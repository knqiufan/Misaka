# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Misaka is a desktop GUI client for Claude Code, built with Python 3.10+ and [Flet](https://flet.dev) 0.80.x (Flutter-based UI framework). It wraps the `claude-agent-sdk` to provide multi-turn streaming conversations, session management, file browsing, MCP server integration, and skill management in a Material Design 3 interface.

**External runtime requirement:** Node.js + `@anthropic-ai/claude-code` CLI installed globally.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run the application
misaka
# or: python -m misaka.main

# Run all tests
pytest

# Run a single test file
pytest tests/unit/test_session_service.py

# Run a single test by name
pytest -k "test_name"

# Lint
ruff check misaka/

# Type check
mypy misaka/

# Build standalone executable
pip install -e ".[build]"
pyinstaller misaka.spec
```

## Architecture

```
UI Layer (Flet controls) → AppState (centralized state) → ServiceContainer (DI) → DatabaseBackend / Claude SDK
```

### Key modules

- **`misaka/main.py`** — Entry point. Creates `DatabaseBackend`, `ServiceContainer`, `AppState`, and `AppShell`. Bootstraps the Flet event loop.
- **`misaka/config.py`** — Paths (`~/.misaka/` data dir), env var helpers, `SettingKeys` constants.
- **`misaka/state.py`** — `AppState` — single mutable state object. Components read from it; services mutate it; `state.update()` triggers Flet re-render.
- **`misaka/commands.py`** — Slash command definitions. `immediate=True` commands are handled in UI; `immediate=False` commands inject prompts to Claude.

### ServiceContainer (misaka/main.py)

Plain class that instantiates all services once and wires dependencies. Services include: `ClaudeService`, `SessionService`, `MessageService`, `ProviderService`, `SettingsService`, `PermissionService`, `MCPService`, `TaskService`, `FileService`, `SkillService`, etc.

### Database layer (misaka/db/)

- `DatabaseBackend` — ABC defining full CRUD interface
- `SQLiteBackend` — sole implementation (stdlib `sqlite3`, WAL mode)
- `create_database()` — factory that returns SQLiteBackend
- Models are plain `@dataclass` objects, no ORM
- Migrations are incremental, idempotent, versioned via `_schema_version` table

### Claude integration (misaka/services/claude_service.py)

- Wraps `claude-agent-sdk` (`ClaudeSDKClient`) with async streaming
- Builds subprocess environment with API keys, expanded PATH, and Windows-specific `.cmd` → `.js` resolution
- Permission flow: SDK callback → `PermissionService.register()` (asyncio.Future) → UI dialog → `PermissionService.resolve()` with 5-minute timeout

### UI layer (misaka/ui/)

- `AppShell` — root `ft.Row`: NavRail + content area switching between ChatPage, SettingsPage, PluginsPage, ExtensionsPage
- Components in `misaka/ui/components/` — reusable Flet controls (chat list, message items, file tree, etc.)
- Pages in `misaka/ui/pages/` — full-page views
- Theme: MD3 with accent `#6366f1`, three modes (system/light/dark), persisted in DB

### i18n

JSON locale files in `misaka/i18n/` (en, zh_CN, zh_TW). Locale change rebuilds all pages via `AppShell.rebuild_for_locale_change()`.

## Code Conventions

- Every module uses `from __future__ import annotations` for Python 3.10 compatibility
- `TYPE_CHECKING` guards on imports used only for type hints (avoids circular imports)
- Line length: 100 characters (Ruff)
- Strict mypy: no implicit `Any`, `warn_return_any = true`
- Ruff rules: E, F, W, I, N, UP, B, A, SIM
- Async dispatch from sync UI handlers: `page.run_task(coro)`
- pytest uses `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed
- Test fixtures in `tests/conftest.py` provide in-memory `SQLiteBackend` via `tmp_path`

## Windows-Specific Notes

- Claude CLI `.cmd` wrappers are resolved to actual `.js` entry points in `ClaudeService`
- Git Bash path is discovered and set via `CLAUDE_CODE_GIT_BASH_PATH` env var
- PATH is expanded with common npm/nvm install locations
- SQLite is the sole database backend on all platforms
