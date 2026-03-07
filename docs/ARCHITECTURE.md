# Misaka Architecture

## Overview

Misaka is a desktop GUI client for Claude Code, built with Python 3.10+ and [Flet](https://flet.dev) (Flutter-based UI framework). It wraps the `claude-agent-sdk` to provide multi-turn streaming conversations, session management, file browsing, MCP server integration, and skill management in a Material Design 3 interface.

## Architecture Layers

```
UI Layer (Flet controls) → AppState (centralized state) → ServiceContainer (DI) → DatabaseBackend / Claude SDK
```

## Directory Structure

```
misaka/
├── main.py                    # Entry point
├── config.py                  # Configuration and paths
├── state.py                   # Centralized application state
├── commands.py                # Slash command definitions
│
├── db/                        # Database layer
│   ├── database.py            # DatabaseBackend ABC and factory
│   ├── sqlite_backend.py      # SQLite implementation
│   ├── models.py              # Data models (dataclasses)
│   ├── migrations.py          # Schema migrations
│   └── row_mappers.py         # DB row to model mapping
│
├── services/                  # Service layer (business logic)
│   ├── chat/                  # Claude conversation services
│   │   ├── claude_service.py      # Claude SDK wrapper
│   │   ├── session_service.py     # Session CRUD
│   │   ├── message_service.py     # Message persistence
│   │   └── permission_service.py  # Permission requests
│   ├── settings/              # Settings management
│   │   ├── settings_service.py    # Key-value settings
│   │   ├── cli_settings_service.py # CLI settings
│   │   └── router_config_service.py # Router config
│   ├── mcp/                   # MCP server management
│   │   └── mcp_service.py
│   ├── skills/                # Skills management
│   │   ├── skill_service.py
│   │   └── env_check_service.py
│   ├── file/                  # File operations
│   │   ├── file_service.py
│   │   └── update_check_service.py
│   ├── task/                  # Task management
│   │   └── task_service.py
│   ├── session/              # Session import
│   │   └── session_import_service.py
│   └── common/                # Shared utilities
│       └── claude_env_builder.py
│
├── ui/                        # UI layer
│   ├── common/                # Shared UI components
│   │   ├── theme.py           # MD3 theme and styling
│   │   └── app_shell.py       # Root layout (NavRail + content)
│   ├── chat/                  # Chat UI
│   │   ├── components/        # Chat-specific components
│   │   │   ├── chat_view.py       # Main chat area
│   │   │   ├── chat_list.py       # Session list
│   │   │   ├── message_list.py   # Message list
│   │   │   ├── message_item.py    # Single message
│   │   │   ├── streaming_message.py
│   │   │   ├── message_input.py
│   │   │   ├── code_block.py
│   │   │   └── tool_call_block.py
│   │   └── pages/
│   │       ├── chat_page.py       # Full chat page
│   │       └── stream_handler.py
│   ├── settings/              # Settings UI
│   │   └── pages/
│   │       ├── settings_page.py
│   │       ├── appearance_section.py
│   │       └── router_config_section.py
│   ├── skills/                # Skills UI
│   │   └── pages/
│   │       ├── skill_editor_panel.py
│   │       └── extensions_page.py
│   ├── file/                  # File UI
│   │   └── components/
│   │       ├── file_tree.py
│   │       ├── file_preview.py
│   │       └── folder_picker.py
│   ├── task/                  # Task UI
│   │   └── components/
│   │       └── task_list.py
│   ├── navigation/
│   │   └── nav_rail.py
│   ├── panels/
│   │   ├── right_panel.py
│   │   ├── resize_handle.py
│   │   └── offset_menu.py
│   ├── dialogs/
│   │   ├── permission_dialog.py
│   │   ├── import_session_dialog.py
│   │   └── env_check_dialog.py
│   └── status/
│       ├── connection_status.py
│       └── update_banner.py
│
├── utils/                     # Utility modules
│   ├── platform.py
│   ├── file_utils.py
│   ├── path_safety.py
│   └── time_utils.py
│
└── i18n/                      # Internationalization
    └── __init__.py
```

## Key Components

### Database Layer

- **DatabaseBackend** (ABC): Defines the CRUD interface for all data operations
- **SQLiteBackend**: Production implementation using stdlib `sqlite3` with WAL mode
- Models are plain `@dataclass` objects, no ORM
- Migrations are incremental, idempotent, versioned via `_schema_version` table

### Service Layer

The `ServiceContainer` in `main.py` holds all service instances and manages dependencies:

- **ClaudeService**: Wraps `claude-agent-sdk` with async streaming, environment setup
- **SessionService/MessageService**: Chat session and message persistence
- **PermissionService**: Manages tool permission requests from Claude SDK
- **SettingsService**: Key-value settings with in-memory caching
- **MCPService**: MCP server lifecycle management

### UI Layer

- **AppShell**: Root layout with navigation rail and content area switching
- Pages are organized by feature (chat, settings, skills, etc.)
- Components are reusable Flet controls
- Theme system with MD3 styling, accent color, and light/dark modes

### State Management

- **AppState**: Single mutable state object for the entire application
- `state.update()` triggers Flet re-render
- Services mutate state; UI components read from it

## Dependency Flow

```
main.py
  ├── creates DatabaseBackend
  ├── creates ServiceContainer (all services)
  ├── creates AppState
  ├── builds AppShell (root UI)
  │
  ├── AppShell
  │   ├── NavRail → page selection
  │   ├── ChatPage
  │   │   ├── ChatList
  │   │   ├── ChatView
  │   │   │   ├── MessageList
  │   │   │   └── MessageInput → ClaudeService
  │   │   └── RightPanel
  │   │       ├── FileTree
  │   │       └── TaskList
  │   ├── SettingsPage → SettingsService
  │   ├── PluginsPage → MCPService
  │   └── ExtensionsPage → SkillService
  │
  └── Services
      ├── db → DatabaseBackend
      ├── claude_service → SDK + env builder
      ├── session_service → db
      ├── message_service → db
      └── ...
```

## Platform-Specific Notes

- Claude CLI `.cmd` wrappers are resolved to actual `.js` entry points in `ClaudeService`
- Git Bash path is discovered and set via `CLAUDE_CODE_GIT_BASH_PATH` env var
- PATH is expanded with common npm/nvm install locations
- SQLite is the sole database backend on all platforms
