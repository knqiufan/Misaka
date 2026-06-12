# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Misaka is a desktop GUI client for Codex, built with Python 3.10+ and [Flet](https://flet.dev) 0.80.x (Flutter-based UI framework). It wraps the `Codex-agent-sdk` to provide multi-turn streaming conversations, session management, file browsing, MCP server integration, skill management, and **knowledge base (RAG)** capabilities in a Material Design 3 interface.

**External runtime requirement:** Node.js + `@anthropic-ai/Codex` CLI installed globally.

## Quick Commands

```bash
# Install and run
pip install -e ".[dev]"
misaka  # or: python -m misaka.main

# Test
pytest
pytest tests/unit/test_session_service.py -k "test_name"

# Lint and type check
ruff check misaka/
mypy misaka/

# Build executable
pip install -e ".[build]"
pyinstaller misaka.spec
```

## Architecture

See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for detailed architecture documentation.

### Core Flow
```
UI Layer (Flet) → AppState → ServiceContainer → Database / Codex SDK
```

### Key Entry Points
- **`misaka/main.py`** — Entry point: creates DatabaseBackend, ServiceContainer, AppState, AppShell
- **`misaka/state.py`** — AppState: single mutable state, `state.update()` triggers re-render
- **`misaka/config.py`** — Configuration and paths (`~/.misaka/`)

### Knowledge Base Module
- **`misaka/services/knowledge/kb_service.py`** — KB lifecycle CRUD, model availability checks, embedding rebuild
- **`misaka/services/knowledge/document_service.py`** — Document upload (hash dedup), delete, reprocess
- **`misaka/services/knowledge/rag_orchestrator.py`** — RAG pipeline: ingest (parse→chunk→embed→store) and retrieve (multi-KB, normalize, rerank)
- **`misaka/services/knowledge/rag/abstractions.py`** — 6 ABC interfaces + data types (framework-agnostic)
- **`misaka/services/knowledge/rag/langchain/`** — LangChain adapter implementations
- **`misaka/ui/knowledge/`** — Knowledge base UI pages and components

## Key Conventions

- See [docs/architecture/CONVENTIONS.md](docs/architecture/CONVENTIONS.md) for full code conventions
- See [docs/architecture/PERFORMANCE.md](docs/architecture/PERFORMANCE.md) for UI performance guidelines

### Critical Rules

1. **UI Performance First**: Always prioritize GUI runtime performance — see [docs/architecture/PERFORMANCE.md](docs/architecture/PERFORMANCE.md)
2. **Flet 0.80.x**: Use `flet` module, not `flutter`; prefer built-in components
3. **Async UI**: Use `page.run_task()` for async operations from sync handlers

## Code Navigation

When the user asks to modify a feature but does not specify exact file paths, **do not search the entire project blindly**. Instead:

1. Read the architecture document at [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) to identify which module handles the described feature
2. Use the "Module Guide: What Each Folder Does" section to locate the relevant `services/` subfolder (business logic) and `ui/` subfolder (interface)
3. Search only within the identified module for the specific code to modify

**Module-to-feature mapping** (quick reference):

| Feature Area | Service Module | UI Module |
|---|---|---|
| Chat / Conversation / Messages | `services/chat/` | `ui/chat/` |
| Knowledge Base / RAG / Documents | `services/knowledge/` | `ui/knowledge/` |
| Settings / Theme / Language | `services/settings/` | `ui/settings/` |
| Skills / Extensions / Marketplace | `services/skills/` | `ui/skills/` |
| MCP Servers / Plugins | `services/mcp/` | `ui/pages/plugins_page.py` |
| File Browser / File Tree | `services/file/` | `ui/file/` |
| Tasks | `services/task/` | `ui/task/` |
| Session Import | `services/session/` | `ui/dialogs/import_session_dialog.py` |
| Dashboard / Statistics | `services/dashboard/` | `ui/dashboard/` |
| Provider Diagnostics | `services/doctor/` | `ui/dialogs/doctor_dialog.py` |
| Images / Thumbnails | `services/images/` | `ui/components/image_overlay.py` |
| Notifications | `services/notification/` | `ui/status/notification_panel.py` |
| Permissions | `services/chat/permission_service.py` | `ui/dialogs/permission_dialog.py` |
| Update Check | `services/file/update_check_service.py` | `ui/status/update_banner.py` |
| Database / Migrations / Models | `db/` | — |
| Navigation / Layout / Theme | — | `ui/common/`, `ui/navigation/` |

## i18n

JSON locale files in `misaka/i18n/` (en, zh_CN, zh_TW). Locale change rebuilds all pages via `AppShell.rebuild_for_locale_change()`.
