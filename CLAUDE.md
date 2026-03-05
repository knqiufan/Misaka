# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Misaka is a desktop GUI client for Claude Code, built with Python 3.10+ and [Flet](https://flet.dev) 0.80.x (Flutter-based UI framework). It wraps the `claude-agent-sdk` to provide multi-turn streaming conversations, session management, file browsing, MCP server integration, and skill management in a Material Design 3 interface.

**External runtime requirement:** Node.js + `@anthropic-ai/claude-code` CLI installed globally.

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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

### Core Flow
```
UI Layer (Flet) → AppState → ServiceContainer → Database / Claude SDK
```

### Key Entry Points
- **`misaka/main.py`** — Entry point: creates DatabaseBackend, ServiceContainer, AppState, AppShell
- **`misaka/state.py`** — AppState: single mutable state, `state.update()` triggers re-render
- **`misaka/config.py`** — Configuration and paths (`~/.misaka/`)

## Key Conventions

- See [docs/CONVENTIONS.md](docs/CONVENTIONS.md) for full code conventions
- See [docs/PERFORMANCE.md](docs/PERFORMANCE.md) for UI performance guidelines

### Critical Rules

1. **UI Performance First**: Always prioritize GUI runtime performance — see [docs/PERFORMANCE.md](docs/PERFORMANCE.md)
2. **Flet 0.80.x**: Use `flet` module, not `flutter`; prefer built-in components
3. **Async UI**: Use `page.run_task()` for async operations from sync handlers

## i18n

JSON locale files in `misaka/i18n/` (en, zh_CN, zh_TW). Locale change rebuilds all pages via `AppShell.rebuild_for_locale_change()`.
