# Misaka Python Rewrite - Architecture Design

**Date:** 2026-02-23
**Status:** Active
**Author:** Architect Agent
**Last Updated:** 2026-02-23 (API research + implementation guides)

---

## 1. Overview

### 1.1 Project Goals

Rewrite Misaka (a desktop GUI client for Claude Code) from Electron+Next.js+React+TypeScript
to a pure-Python stack: **Flet** for the UI, **Claude Agent SDK (Python)** for AI integration,
and **SQLite** for persistence (SeekDB optional on Linux).

Key motivations:
- Eliminate the Node.js/Electron dependency chain and native module headaches (better-sqlite3 ABI)
- Simplify packaging (single PyInstaller binary vs Electron+Next.js standalone)
- Leverage Python ecosystem for AI/ML tooling
- Reduce build complexity on Windows (no .cmd wrapper resolution, no taskkill tree-kill)

### 1.2 Technology Stack

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| UI Framework | Flet | >= 0.27.0, < 1.0 | Flutter-based, reactive, cross-platform |
| AI Integration | claude-agent-sdk | >= 0.1.5 | Official Anthropic SDK, async, subprocess-based |
| Database (all platforms) | SQLite3 (stdlib) | Python stdlib | Primary backend, WAL mode |
| Database (Linux, optional) | SeekDB (pyseekdb) | >= 1.0.0 | Embedded mode, Linux only |
| File Watching | watchdog | >= 4.0.0 | Cross-platform FS events |
| Syntax Highlighting | Pygments | >= 2.18.0 | For file previews and code blocks |
| Async Runtime | anyio | >= 4.0.0 | Required by claude-agent-sdk |
| Packaging | PyInstaller | >= 6.0 | Single-file or one-directory bundles |

### 1.3 Migration Strategy

The rewrite is a clean-room implementation guided by the existing TypeScript codebase.
No code is ported line-by-line; instead, we replicate the same **user-facing behavior**
and **data model** using idiomatic Python patterns.

Phase 1: Core scaffold, database, config, state management (DONE)
Phase 2: Claude service integration - streaming, permissions, MCP (IN PROGRESS)
Phase 3: UI components - chat, file tree, settings (IN PROGRESS)
Phase 4: Packaging, testing, polish (PENDING)

---

## 2. Architecture

### 2.1 Layer Diagram

```
┌──────────────────────────────────────────────────────────┐
│                      Flet UI Layer                        │
│  ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │NavRail │ │ ChatList  │ │ ChatView │ │ RightPanel   │  │
│  │        │ │  Panel    │ │ (center) │ │ (files/tasks)│  │
│  └────────┘ └──────────┘ └──────────┘ └──────────────┘  │
├──────────────────────────────────────────────────────────┤
│                    State Manager                          │
│  (AppState: reactive, drives UI updates via page.update) │
├──────────────────────────────────────────────────────────┤
│                    Service Layer                          │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ClaudeService│ │SessionService│ │  FileService     │  │
│  │(SDK client) │ │(CRUD + state)│ │(tree, preview)   │  │
│  └─────────────┘ └──────────────┘ └──────────────────┘  │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ MCPService  │ │SettingsServ. │ │ PermissionServ.  │  │
│  └─────────────┘ └──────────────┘ └──────────────────┘  │
├──────────────────────────────────────────────────────────┤
│                   Database Layer                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │  DatabaseBackend (ABC)                            │    │
│  │  ├─ SeekDBBackend  (Linux, embedded, optional)    │    │
│  │  └─ SQLiteBackend  (all platforms, primary)       │    │
│  └──────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────┤
│                    Utilities                              │
│  platform.py · path_safety.py · file_utils.py            │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

1. User types a message in `MessageInput`
2. `ChatView` calls `ClaudeService.send_message(session_id, prompt)`
3. `ClaudeService` creates `ClaudeAgentOptions` and calls `query()` or uses `ClaudeSDKClient`
4. The SDK spawns a Claude Code CLI subprocess and streams messages via JSON
5. As `AssistantMessage` objects arrive, `AppState.streaming_blocks` is updated
6. `StreamingMessage` component re-renders via `page.update()`
7. On `ResultMessage`, the full message is persisted via `MessageService.save_message()`
8. `AppState.messages` list is updated, triggering `MessageList` re-render

### 2.3 Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `main.py` | Flet app entry point, page setup, routing |
| `config.py` | Data dir paths, env var loading, platform detection |
| `state.py` | Global reactive state (current session, messages, panels) |
| `ui/app_shell.py` | Root layout: nav rail + 3-panel split |
| `ui/theme.py` | Dark/light themes, color tokens |
| `services/claude_service.py` | Claude SDK wrapper: query, stream, permissions |
| `services/session_service.py` | Session CRUD, timestamp updates |
| `services/message_service.py` | Message persistence, content parsing |
| `services/file_service.py` | Directory scanning, file preview, path safety |
| `services/mcp_service.py` | MCP server config loading and management |
| `services/provider_service.py` | API provider CRUD, activation |
| `services/permission_service.py` | Permission request/response registry |
| `services/settings_service.py` | Settings key-value store |
| `services/task_service.py` | Task CRUD per session |
| `db/database.py` | Backend ABC + factory |
| `db/models.py` | Dataclass models |
| `db/seekdb_backend.py` | SeekDB implementation |
| `db/sqlite_backend.py` | SQLite implementation |
| `db/migrations.py` | Schema versioning |

---

## 3. Database Design

### 3.1 Schema

All backends implement the same logical schema. SeekDB uses collections with
JSON documents; SQLite uses relational tables.

#### chat_sessions

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID hex string |
| title | TEXT | Default 'New Chat' |
| model | TEXT | e.g. 'claude-sonnet-4-5' |
| system_prompt | TEXT | Custom system prompt |
| working_directory | TEXT | Project path |
| project_name | TEXT | Derived from working_directory |
| sdk_session_id | TEXT | For SDK session resume |
| status | TEXT | 'active' or 'archived' |
| mode | TEXT | 'code', 'plan', or 'ask' |
| created_at | TEXT | ISO datetime |
| updated_at | TEXT | ISO datetime |

#### messages

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID hex string |
| session_id | TEXT FK | References chat_sessions.id |
| role | TEXT | 'user' or 'assistant' |
| content | TEXT | JSON string of content blocks |
| token_usage | TEXT | JSON string of TokenUsage, nullable |
| created_at | TEXT | ISO datetime |

#### tasks

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID hex string |
| session_id | TEXT FK | References chat_sessions.id |
| title | TEXT | Task title |
| status | TEXT | pending/in_progress/completed/failed |
| description | TEXT | Nullable |
| created_at | TEXT | ISO datetime |
| updated_at | TEXT | ISO datetime |

#### api_providers

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID hex string |
| name | TEXT | Display name |
| provider_type | TEXT | 'anthropic', 'openrouter', etc. |
| base_url | TEXT | API base URL |
| api_key | TEXT | API key (stored locally) |
| is_active | INTEGER | 0 or 1 |
| sort_order | INTEGER | Display ordering |
| extra_env | TEXT | JSON of extra env vars |
| notes | TEXT | User notes |
| created_at | TEXT | ISO datetime |
| updated_at | TEXT | ISO datetime |

#### settings

| Column | Type | Notes |
|--------|------|-------|
| key | TEXT PK | Setting key |
| value | TEXT | JSON-encoded value |

### 3.2 SeekDB Implementation Notes

SeekDB (pyseekdb) operates in **embedded mode** on Linux **only**:

```python
import pyseekdb
client = pyseekdb.Client(path="~/.misaka/misaka.db", database="misaka")
collection = client.get_or_create_collection("chat_sessions")
```

Each table maps to a SeekDB collection. Documents are stored as JSON with
metadata fields for indexing. Queries use `collection.query()` with filters.

**Platform limitation (CONFIRMED 2026-02)**: SeekDB embedded mode is supported
on **Linux only**. macOS and Windows require a SeekDB server process (client/server
mode), which adds deployment complexity. For simplicity, Misaka uses SQLite
as the primary backend on all platforms, with SeekDB as an optional backend on
Linux for users who want vector search capabilities.

### 3.3 SQLite Implementation Notes

Uses Python's stdlib `sqlite3` module with WAL mode enabled.
Schema matches the TypeScript version exactly for data migration compatibility.
The same SQL DDL from the original `db.ts` is reused.

---

## 4. UI Architecture

### 4.1 CRITICAL: Flet Version Compatibility

**Flet version pinning: `>= 0.27.0, < 1.0`**

Key API changes to be aware of:

1. **`UserControl` is deprecated and will be removed in Flet 1.0 (already removed
   in Flet 0.28.2 as part of "Remove Flet v0.25 deprecations").** Our current code
   uses `ft.UserControl` extensively. **All components MUST be migrated** to one of:
   - Direct inheritance from a container control (e.g., `ft.Column`, `ft.Container`)
   - Composition using factory functions that return `ft.Control` instances
   - The new `@ft.component` / `@ft.memo` decorators (Flet 0.80+ declarative style)

2. **Recommended migration pattern** (for Flet 0.27-0.28):
   Instead of:
   ```python
   class MyWidget(ft.UserControl):
       def build(self) -> ft.Control:
           return ft.Container(content=...)
   ```
   Use:
   ```python
   class MyWidget(ft.Container):
       def __init__(self, **kwargs):
           super().__init__(**kwargs)
           self.content = ft.Column(controls=[...])
   ```
   Or use factory functions:
   ```python
   def create_my_widget(state: AppState) -> ft.Control:
       return ft.Container(content=ft.Column(controls=[...]))
   ```

3. **Flet 0.27.0 changes**: `Dropdown` widget was replaced with `DropdownMenu`
   internally; `ControlEvent.data` is now `Optional[str]` with `None` default;
   v0.24.0 deprecations removed.

4. **Flet 0.28.2 changes**: v0.25 deprecations removed (including `UserControl`
   removal path). Must test against this version.

### 4.2 Component Tree

```
ft.app(target=main)
└── AppShell (Row)
    ├── NavRail (NavigationRail)
    │   ├── Chat destination
    │   ├── Settings destination
    │   └── Plugins destination
    ├── ChatListPanel (Column, collapsible)
    │   ├── Search field
    │   └── ListView of ChatListItem
    ├── CenterPanel (Column, flex)
    │   ├── Header (Row: title, model selector, mode toggle)
    │   ├── MessageList (ListView, scrollable)
    │   │   └── MessageItem (Column)
    │   │       ├── TextBlock -> Markdown
    │   │       ├── ToolCallBlock (expandable)
    │   │       └── CodeBlock (syntax highlighted)
    │   ├── StreamingMessage (live updating)
    │   └── MessageInput (TextField + send button)
    └── RightPanel (Column, collapsible)
        ├── FileTree (TreeView)
        ├── FilePreview (code viewer)
        └── TaskList (ListView of TaskCard)
```

### 4.3 State Management Pattern

Flet uses an imperative update model: mutate state, then call `page.update()`.
We centralize state in `AppState` (a plain Python class) and provide methods
that update state + trigger UI refresh.

```python
class AppState:
    def __init__(self, page: ft.Page):
        self.page = page
        self.current_session_id: str | None = None
        self.sessions: list[ChatSession] = []
        self.messages: list[Message] = []
        self.streaming_blocks: list[ContentBlock] = []
        self.is_streaming: bool = False
        # Panel visibility
        self.left_panel_open: bool = True
        self.right_panel_open: bool = True
        # Theme
        self.theme_mode: str = "system"

    def update(self):
        """Trigger UI refresh."""
        self.page.update()
```

Components hold a reference to `AppState` and read from it during build.
Service methods mutate `AppState` and call `state.update()` when done.

**Thread safety note:** Flet's `page.update()` is safe to call from any thread.
However, since `ClaudeService` runs async operations, we must ensure that
streaming callbacks that update `AppState` and call `state.update()` are
properly scheduled. Use `page.run_task()` to schedule async work from
synchronous contexts, or use `asyncio.create_task()` within an existing
async context.

### 4.4 Theming

Flet supports Material Design 3 themes. We define a custom `ThemeData`
with Misaka's color palette:

- Dark mode: deep gray background (#1a1a2e), accent blue (#4361ee)
- Light mode: white background, same accent blue
- System mode: follows OS preference

The `theme.py` module exports `get_theme(mode)` returning `ft.Theme`.

### 4.5 UI Component Implementation Patterns

Each UI component should follow this pattern:

```python
class ChatListPanel(ft.Column):
    """Chat session list sidebar."""

    def __init__(self, state: AppState, db: DatabaseBackend):
        super().__init__(spacing=0, expand=True)
        self.state = state
        self.db = db
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the initial UI structure."""
        self.search_field = ft.TextField(
            hint_text="Search sessions...",
            on_change=self._on_search,
            prefix_icon=ft.icons.SEARCH,
        )
        self.session_list = ft.ListView(
            expand=True,
            spacing=2,
            auto_scroll=False,
        )
        self.controls = [
            ft.Container(content=self.search_field, padding=8),
            ft.Divider(height=1),
            self.session_list,
        ]

    def refresh(self) -> None:
        """Rebuild the session list from state."""
        self.session_list.controls = [
            self._build_session_item(s)
            for s in self.state.sessions
        ]

    def _build_session_item(self, session: ChatSession) -> ft.Control:
        """Build a single session list item."""
        is_selected = session.id == self.state.current_session_id
        return ft.ListTile(
            title=ft.Text(session.title, max_lines=1),
            subtitle=ft.Text(session.project_name or "", size=11),
            selected=is_selected,
            on_click=lambda e, sid=session.id: self._on_select(sid),
        )

    def _on_select(self, session_id: str) -> None:
        self.state.current_session_id = session_id
        # Load messages for this session...
        self.state.update()

    def _on_search(self, e: ft.ControlEvent) -> None:
        query = (e.data or "").lower()
        # Filter sessions by title...
        self.state.update()
```

---

## 5. Claude Integration

### 5.1 SDK Package Details (VERIFIED 2026-02-23)

**Package name:** `claude-agent-sdk` (PyPI)
**Import name:** `claude_agent_sdk`
**Current version:** 0.1.5
**Repository:** https://github.com/anthropics/claude-code-sdk-python

The SDK communicates with Claude Code via a **subprocess** running the Claude Code
CLI (`@anthropic-ai/claude-code` npm package). The CLI must be installed separately
(`npm install -g @anthropic-ai/claude-code`). Since SDK version 0.1.8, the CLI is
bundled with the SDK automatically.

**Two interaction modes:**

1. **`query()` function** - Simple one-shot, stateless queries. Returns
   `AsyncIterator[Message]`. Best for fire-and-forget operations.

2. **`ClaudeSDKClient` class** - Bidirectional, stateful conversations.
   Supports interrupts, follow-up messages, dynamic permission mode changes,
   and model switching. Best for interactive chat UIs.

**For Misaka, we should use `ClaudeSDKClient`** for the main chat interaction
because it supports:
- Multi-turn conversations with state
- Interrupt capabilities (user can stop generation)
- Dynamic permission mode changes
- Session management

### 5.2 ClaudeService Implementation

```python
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    UserMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ThinkingBlock,
    StreamEvent,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from misaka.config import IS_WINDOWS, get_expanded_path
from misaka.db.database import DatabaseBackend
from misaka.db.models import ApiProvider
from misaka.utils.platform import find_claude_binary, find_git_bash

logger = logging.getLogger(__name__)


class ClaudeService:
    """Service for interacting with Claude Code via the Agent SDK."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db
        self._client: ClaudeSDKClient | None = None
        self._is_streaming = False

    def _build_env(self, provider: ApiProvider | None = None) -> dict[str, str]:
        """Build the subprocess environment for the Claude CLI."""
        import os
        env: dict[str, str] = {k: v for k, v in os.environ.items() if isinstance(v, str)}

        home = str(Path.home())
        env.setdefault("HOME", home)
        env.setdefault("USERPROFILE", home)
        env["PATH"] = get_expanded_path()

        if IS_WINDOWS and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
            git_bash = find_git_bash()
            if git_bash:
                env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash

        if provider and provider.api_key:
            for key in list(env.keys()):
                if key.startswith("ANTHROPIC_"):
                    del env[key]
            env["ANTHROPIC_AUTH_TOKEN"] = provider.api_key
            env["ANTHROPIC_API_KEY"] = provider.api_key
            if provider.base_url:
                env["ANTHROPIC_BASE_URL"] = provider.base_url
            for key, value in provider.parse_extra_env().items():
                if value == "":
                    env.pop(key, None)
                else:
                    env[key] = value
        else:
            legacy_token = self._db.get_setting("anthropic_auth_token")
            legacy_base = self._db.get_setting("anthropic_base_url")
            if legacy_token:
                env["ANTHROPIC_AUTH_TOKEN"] = legacy_token
            if legacy_base:
                env["ANTHROPIC_BASE_URL"] = legacy_base

        return env

    def _build_options(
        self,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        working_directory: str | None = None,
        sdk_session_id: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        permission_mode: str = "acceptEdits",
        provider: ApiProvider | None = None,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from parameters."""
        cwd = working_directory or str(Path.home())
        env = self._build_env(provider)

        options = ClaudeAgentOptions(
            cwd=cwd,
            system_prompt=system_prompt,
            permission_mode=permission_mode,  # type: ignore[arg-type]
            env=env,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep",
                           "WebFetch", "WebSearch"],
        )

        if sdk_session_id:
            options.resume = sdk_session_id

        if model:
            options.model = model

        if mcp_servers:
            options.mcp_servers = mcp_servers

        return options

    async def send_message(
        self,
        session_id: str,
        prompt: str,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        working_directory: str | None = None,
        sdk_session_id: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        permission_mode: str = "acceptEdits",
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[dict[str, Any]], None] | None = None,
        on_status: Callable[[dict[str, Any]], None] | None = None,
        on_result: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_permission_request: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        """Send a message to Claude and stream the response.

        Uses ClaudeSDKClient for bidirectional communication.
        """
        self._is_streaming = True

        # Get active provider
        provider = self._db.get_active_provider()

        options = self._build_options(
            model=model,
            system_prompt=system_prompt,
            working_directory=working_directory,
            sdk_session_id=sdk_session_id,
            mcp_servers=mcp_servers,
            permission_mode=permission_mode,
            provider=provider,
        )

        # Set up permission callback if handler provided
        if on_permission_request:
            async def _can_use_tool(
                tool_name: str,
                tool_input: dict[str, Any],
                context: ToolPermissionContext,
            ):
                # Forward to UI for user decision
                result = on_permission_request({
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "suggestions": [s.to_dict() for s in context.suggestions],
                })
                # result should be a Future that resolves to True/False
                if asyncio.isfuture(result):
                    decision = await result
                else:
                    decision = result

                if decision:
                    return PermissionResultAllow(updated_input=tool_input)
                else:
                    return PermissionResultDeny(message="User denied permission")

            options.can_use_tool = _can_use_tool

        try:
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect(prompt)

            async for message in self._client.receive_response():
                if not self._is_streaming:
                    break

                match message:
                    case AssistantMessage():
                        for block in message.content:
                            match block:
                                case TextBlock(text=text):
                                    if on_text:
                                        on_text(text)
                                case ToolUseBlock(id=tool_id, name=name, input=inp):
                                    if on_tool_use:
                                        on_tool_use({
                                            "id": tool_id,
                                            "name": name,
                                            "input": inp,
                                        })
                                case ToolResultBlock(
                                    tool_use_id=tool_use_id,
                                    content=content,
                                    is_error=is_error,
                                ):
                                    if on_tool_result:
                                        on_tool_result({
                                            "tool_use_id": tool_use_id,
                                            "content": content,
                                            "is_error": is_error,
                                        })
                                case ThinkingBlock(thinking=thinking):
                                    if on_status:
                                        on_status({
                                            "type": "thinking",
                                            "content": thinking,
                                        })

                    case ResultMessage():
                        if on_result:
                            on_result({
                                "session_id": message.session_id,
                                "duration_ms": message.duration_ms,
                                "is_error": message.is_error,
                                "num_turns": message.num_turns,
                                "total_cost_usd": message.total_cost_usd,
                                "usage": message.usage,
                            })

                    case SystemMessage():
                        if on_status:
                            on_status({
                                "type": "system",
                                "subtype": message.subtype,
                                "data": message.data,
                            })

        except Exception as exc:
            logger.error("ClaudeService.send_message error: %s", exc, exc_info=True)
            if on_error:
                on_error(str(exc))
        finally:
            self._is_streaming = False
            if self._client:
                await self._client.disconnect()
                self._client = None

    async def abort(self) -> None:
        """Abort the current streaming operation."""
        self._is_streaming = False
        if self._client:
            try:
                await self._client.interrupt()
            except Exception as exc:
                logger.warning("Error interrupting client: %s", exc)
            try:
                await self._client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting client: %s", exc)
            self._client = None
```

### 5.3 Permission Flow

The SDK supports a `can_use_tool` callback for interactive permission approval.
This requires the `ClaudeSDKClient` (streaming mode), not `query()`.

```python
async def permission_handler(tool_name, tool_input, context):
    """Push permission request to UI via AppState, wait for user response."""
    future = asyncio.get_event_loop().create_future()
    state.pending_permission = PermissionRequest(
        id=generate_id(),
        tool_name=tool_name,
        tool_input=tool_input,
        suggestions=[s.to_dict() for s in context.suggestions],
    )
    state._permission_future = future
    state.update()  # Triggers PermissionDialog to appear

    # Wait for user to approve/deny in PermissionDialog
    decision = await future

    if decision:
        return PermissionResultAllow(updated_input=tool_input)
    else:
        return PermissionResultDeny(message="User denied permission")
```

**UI side (PermissionDialog):**

```python
def _on_approve(self, e):
    if self.state._permission_future and not self.state._permission_future.done():
        self.state._permission_future.set_result(True)
    self.state.pending_permission = None
    self.state.update()

def _on_deny(self, e):
    if self.state._permission_future and not self.state._permission_future.done():
        self.state._permission_future.set_result(False)
    self.state.pending_permission = None
    self.state.update()
```

### 5.4 MCP Server Support

MCP servers are configured in `~/.claude.json` or `~/.claude/settings.json`.
The `MCPService` reads these configs and converts them to SDK format.

The SDK supports four MCP transport types:

```python
from claude_agent_sdk.types import (
    McpStdioServerConfig,   # subprocess-based
    McpSSEServerConfig,      # Server-Sent Events
    McpHttpServerConfig,     # HTTP
    McpSdkServerConfig,      # In-process SDK server
)
```

For Misaka, we primarily use `McpStdioServerConfig` (matching the original
TypeScript behavior). The `MCPService.to_sdk_format()` already handles this
conversion correctly.

**Important:** MCP server config can also be passed as a `str | Path` pointing
to a JSON config file, which the SDK will read directly:

```python
options.mcp_servers = "~/.claude/mcp-servers.json"
```

### 5.5 Environment Variable Management

The `ClaudeService` builds the subprocess environment:
1. Start with `os.environ`
2. Overlay active provider's API key and base URL
3. Apply `extra_env` from provider config (empty string = delete var)
4. Set HOME/USERPROFILE, expand PATH
5. Pass via `ClaudeAgentOptions.env`

### 5.6 Session Resume

The SDK supports resuming previous sessions via the `resume` option:

```python
options = ClaudeAgentOptions(resume="session-uuid-here")
```

When a `ResultMessage` is received, store `message.session_id` in the database
via `update_sdk_session_id()`. On the next message in the same session, pass
that ID as `resume` to continue the conversation.

For forking (creating a new conversation branch from an existing session):

```python
options = ClaudeAgentOptions(resume="session-uuid", fork_session=True)
```

### 5.7 Streaming Events (Partial Messages)

For real-time UI updates during text generation, enable partial messages:

```python
options = ClaudeAgentOptions(include_partial_messages=True)
```

This yields `StreamEvent` objects with raw Anthropic API stream events,
which can be used to show text as it's being generated character by character.

---

## 6. Error Handling Strategy

### 6.1 SDK Error Types

The SDK defines these error classes:

| Error | When | Recovery |
|-------|------|----------|
| `CLINotFoundError` | Claude Code CLI not installed | Show install instructions in UI |
| `CLIConnectionError` | Subprocess failed to start/connect | Retry with backoff, check PATH |
| `CLIJSONDecodeError` | Malformed CLI output | Log and skip malformed message |
| `ProcessError` | CLI process exited with error | Show error message, allow retry |
| `ClaudeSDKError` | Base class for all SDK errors | Generic error handling |

### 6.2 Error Handling Pattern

```python
from claude_agent_sdk import (
    ClaudeSDKError,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
)

try:
    async for message in client.receive_response():
        # Process messages...
        pass
except CLINotFoundError:
    state.error_message = (
        "Claude Code CLI not found. Please install it with:\n"
        "npm install -g @anthropic-ai/claude-code"
    )
    state.update()
except CLIConnectionError as e:
    state.error_message = f"Failed to connect to Claude: {e}"
    state.update()
except ProcessError as e:
    state.error_message = f"Claude process error: {e}"
    state.update()
except ClaudeSDKError as e:
    state.error_message = f"SDK error: {e}"
    state.update()
except Exception as e:
    logger.error("Unexpected error: %s", e, exc_info=True)
    state.error_message = f"Unexpected error: {e}"
    state.update()
finally:
    state.clear_streaming()
    state.update()
```

### 6.3 UI Error Display

Errors should be displayed as a dismissible banner at the top of the chat area:

```python
class ErrorBanner(ft.Container):
    def __init__(self, state: AppState):
        super().__init__(visible=False)
        self.state = state

    def refresh(self):
        if self.state.error_message:
            self.visible = True
            self.content = ft.Row([
                ft.Icon(ft.icons.ERROR, color=ft.colors.RED),
                ft.Text(self.state.error_message, expand=True),
                ft.IconButton(
                    icon=ft.icons.CLOSE,
                    on_click=self._dismiss,
                ),
            ])
        else:
            self.visible = False

    def _dismiss(self, e):
        self.state.clear_error()
        self.state.update()
```

---

## 7. File System

### 7.1 Security Model

All file operations validate paths using `path_safety.is_path_safe(base, target)`:
- Target must be under base directory (no traversal via `..`)
- Root paths (`/`, `C:\`) are rejected as base directories
- Symlinks are resolved before comparison

### 7.2 File Watching

`watchdog.Observer` monitors the working directory for changes.
Events are debounced (300ms) and trigger a re-scan of the file tree.

### 7.3 Directory Scanning

`file_service.scan_directory(path, depth=3)` returns a tree of `FileTreeNode`.
Ignores: `node_modules`, `.git`, `dist`, `__pycache__`, `.next`, etc.
Files include name, path, size, and extension.

### 7.4 File Preview

`file_service.read_file_preview(path, max_lines=200)` returns content
with language detection via extension mapping (same as TypeScript version).

---

## 8. Performance Optimization Strategy

### 8.1 Message List Virtualization

For sessions with many messages, use Flet's `ListView` with `auto_scroll`
and lazy loading:

```python
message_list = ft.ListView(
    expand=True,
    spacing=4,
    auto_scroll=True,  # Scroll to bottom on new messages
)
```

For infinite scroll (loading older messages), detect scroll position and
load more messages when the user scrolls to the top. Use cursor-based
pagination via `db.get_messages(session_id, before_rowid=...)`.

### 8.2 Streaming Update Throttling

During streaming, `page.update()` can be expensive if called for every token.
Throttle updates to ~30fps (every 33ms):

```python
import time

class StreamingThrottler:
    def __init__(self, min_interval_ms: int = 33):
        self._min_interval = min_interval_ms / 1000
        self._last_update = 0.0
        self._pending = False

    def should_update(self) -> bool:
        now = time.monotonic()
        if now - self._last_update >= self._min_interval:
            self._last_update = now
            self._pending = False
            return True
        self._pending = True
        return False

    def has_pending(self) -> bool:
        return self._pending
```

### 8.3 Database Query Optimization

- Use WAL mode for concurrent reads during streaming
- Batch message inserts when saving assistant responses (which may contain
  multiple content blocks)
- Index on `session_id` and `created_at` for message queries
- Limit session list to most recent 100 by default

### 8.4 File Tree Scanning

- Scan only to depth=3 by default
- Cache the file tree and invalidate on watchdog events
- Use a debounced re-scan (300ms) to avoid thrashing on rapid file changes

---

## 9. Packaging

### 9.1 PyInstaller Configuration

```
pyinstaller --name Misaka \
    --windowed \
    --onedir \
    --icon build/icon.ico \
    --add-data "misaka/ui:misaka/ui" \
    misaka/main.py
```

### 9.2 Platform-Specific Considerations

| Platform | Notes |
|----------|-------|
| macOS | .app bundle, codesign required for distribution |
| Windows | .exe in directory, no admin required. SQLite-only mode. |
| Linux | AppImage or directory. SeekDB embedded works. |

### 9.3 Build Matrix

CI builds for:
- macOS arm64 (Apple Silicon)
- macOS x64 (Intel)
- Windows x64
- Linux x64

---

## 10. Cross-Platform

### 10.1 Windows Limitations

- **SeekDB**: Embedded mode not supported. Always use SQLite backend.
- **Path separators**: Use `pathlib.Path` everywhere, avoid hardcoded `/`.
- **Process cleanup**: Use `taskkill /T /F /PID` for tree-kill on Windows.
- **Shell**: No bash by default; Claude SDK handles this internally.

### 10.2 Path Handling

All path operations use `pathlib.Path` for cross-platform compatibility.
`config.py` provides `DATA_DIR`, `DB_PATH` etc. as `Path` objects.

### 10.3 Platform Detection

```python
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"
```

Used to select database backend, adjust PATH expansion, and handle
platform-specific UI behaviors (e.g., title bar style).

---

## 11. Implementation Guides

### 11.1 Frontend Team (UI) Implementation Guide

**Priority order:**

1. **Migrate all `UserControl` subclasses** to direct container inheritance.
   Every file in `misaka/ui/components/` currently uses `ft.UserControl`.
   Replace with inheritance from the appropriate base control (`ft.Column`,
   `ft.Container`, `ft.Row`, etc.).

2. **AppShell** (`ui/app_shell.py`):
   - Replace `UserControl` with `ft.Row`
   - Wire up navigation to actually switch pages
   - Add `ResizeHandle` between panels for drag-to-resize
   - Connect to real `ChatListPanel`, `ChatView`, `RightPanel` components

3. **ChatView** (`ui/components/chat_view.py`):
   - Build the message input with `TextField(multiline=True)`
   - Handle send button click: call `ClaudeService.send_message()` via async task
   - Implement `MessageList` as `ListView` with lazy loading
   - Show `StreamingMessage` during active streaming
   - Show model selector dropdown and mode toggle in header

4. **MessageItem** (`ui/components/message_item.py`):
   - Render markdown text using `ft.Markdown` control
   - Render tool calls as expandable/collapsible sections
   - Render code blocks with syntax highlighting via Pygments
   - Style differently for user vs assistant messages

5. **ChatListPanel** (`ui/components/chat_list.py`):
   - Show all sessions from `state.sessions`
   - Highlight currently selected session
   - Support search filtering
   - Support right-click context menu (rename, delete, archive)
   - New chat button

6. **SettingsPage** (`ui/pages/settings_page.py`):
   - API provider management (add/edit/delete/activate)
   - Theme selector (dark/light/system)
   - Default model selection
   - Permission mode selection
   - Working directory selector

7. **RightPanel** (`ui/components/right_panel.py`):
   - Tab switching between Files and Tasks
   - FileTree using nested `ft.ExpansionTile` or custom tree
   - FilePreview with syntax highlighting
   - TaskList with status badges

8. **PermissionDialog** (`ui/components/permission_dialog.py`):
   - Modal dialog showing tool name and input
   - Approve/Deny buttons
   - Connect to `state._permission_future`

**Key Flet patterns to use:**

```python
# Async event handler
async def _on_send(self, e):
    prompt = self.input_field.value
    if not prompt:
        return
    self.input_field.value = ""
    self.state.update()
    # Run the Claude query in background
    self.page.run_task(self._send_message, prompt)

async def _send_message(self, prompt: str):
    await self.claude_service.send_message(
        session_id=self.state.current_session_id,
        prompt=prompt,
        on_text=self._on_streaming_text,
        on_result=self._on_result,
        on_error=self._on_error,
    )
```

### 11.2 Backend Team Implementation Guide

**Priority order:**

1. **ClaudeService full implementation** (`services/claude_service.py`):
   - Replace the stub with the `ClaudeSDKClient`-based implementation shown
     in Section 5.2
   - Implement `_build_options()` with all parameters
   - Implement `abort()` using `client.interrupt()` + `client.disconnect()`
   - Handle all message types: `AssistantMessage`, `ResultMessage`,
     `SystemMessage`, `StreamEvent`
   - Handle error types: `CLINotFoundError`, `CLIConnectionError`, `ProcessError`

2. **Permission handling integration**:
   - Implement the `can_use_tool` callback pattern from Section 5.3
   - Wire the `asyncio.Future` to `AppState.pending_permission`
   - Ensure the Future is resolved from the UI thread when user clicks
     approve/deny

3. **MCP service update** (`services/mcp_service.py`):
   - Current implementation is correct for stdio/sse/http
   - Add support for passing MCP config as a file path string
   - Consider adding SDK MCP server support for in-process tools

4. **Session resume flow**:
   - On `ResultMessage`, save `message.session_id` to database
   - On next message in same session, pass `resume=sdk_session_id`
   - Handle `fork_session` option for conversation branching

5. **Message persistence**:
   - After streaming completes, serialize the full response as JSON content blocks
   - Map SDK `TextBlock` -> `{"type": "text", "text": "..."}`
   - Map SDK `ToolUseBlock` -> `{"type": "tool_use", "id": "...", "name": "...", "input": {...}}`
   - Map SDK `ToolResultBlock` -> `{"type": "tool_result", "tool_use_id": "...", "content": "..."}`
   - Save token usage from `ResultMessage.usage`

6. **Streaming state management**:
   - `on_text` callback: append text to current `StreamingTextBlock` in
     `state.streaming_blocks`, call `state.update()` (throttled)
   - `on_tool_use` callback: add new `StreamingToolUseBlock`, call `state.update()`
   - `on_tool_result` callback: update matching tool block with output
   - `on_result` callback: clear streaming state, persist full message, reload
     messages from DB

7. **Provider service** (`services/provider_service.py`):
   - Ensure `get_active_provider()` returns the provider with `is_active=1`
   - The env build in `ClaudeService._build_env()` already handles provider overlay

---

## 12. TODO Checklist

### Database Layer (95% complete)
- [x] DatabaseBackend ABC
- [x] SQLiteBackend implementation
- [x] SeekDBBackend implementation
- [x] Schema migrations
- [x] Data models
- [ ] Add database connection pooling or thread-safety wrapper

### Service Layer (40% complete)
- [x] SessionService
- [x] MessageService
- [x] FileService
- [x] MCPService
- [x] ProviderService
- [x] PermissionService
- [x] SettingsService
- [x] TaskService
- [ ] **ClaudeService full implementation** (currently stub)
- [ ] Permission callback integration with asyncio.Future
- [ ] Session resume flow
- [ ] Streaming state management with throttling
- [ ] Message serialization from SDK types to DB format

### UI Layer (25% complete)
- [x] AppShell skeleton
- [x] Theme system
- [x] Component file structure
- [ ] **Migrate all UserControl subclasses** (CRITICAL - blocks all UI work)
- [ ] ChatListPanel with real session data
- [ ] ChatView with MessageList, StreamingMessage, MessageInput
- [ ] MessageItem with Markdown, tool call blocks, code blocks
- [ ] RightPanel with FileTree, FilePreview, TaskList
- [ ] SettingsPage with provider management
- [ ] PermissionDialog
- [ ] ConnectionStatus indicator
- [ ] ResizeHandle for panel resizing
- [ ] Keyboard shortcuts (Ctrl+Enter to send, Escape to abort)
- [ ] Model selector dropdown
- [ ] Mode toggle (code/plan/ask)

### Testing (done for existing features, needs expansion)
- [x] Database unit tests
- [x] Path safety unit tests
- [x] File service unit tests
- [x] State unit tests
- [x] Integration tests for session management
- [ ] ClaudeService integration tests (mock subprocess)
- [ ] UI component tests (Flet testing utilities)
- [ ] Permission flow end-to-end test
- [ ] Streaming throttle tests

### Packaging & CI
- [ ] PyInstaller spec file
- [ ] GitHub Actions build matrix
- [ ] macOS code signing
- [ ] Windows installer (NSIS or zip)
- [ ] Linux AppImage
