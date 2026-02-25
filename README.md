# Misaka

**[中文说明](README_CN.md)** · [English](README.md)

> A desktop GUI client for Claude Code, built with Python and [Flet](https://flet.dev).

Misaka brings the power of Claude Code to a polished native desktop experience — multi-turn streaming conversations, session management, file tree browsing, MCP server integration, and more, all wrapped in a clean Material Design 3 interface.

---

## ✨ Features

| Category | Details |
|---|---|
| **Multi-model chat** | Switch between Claude Sonnet, Opus, and Haiku within any session |
| **Streaming responses** | Real-time token-by-token rendering with abort support |
| **Session management** | Create, rename, archive, delete, and search conversation sessions |
| **Three conversation modes** | `Code` · `Plan` · `Ask` — maps directly to Claude Code's native modes |
| **File tree browser** | Browse your project directory in the right panel with live file preview |
| **MCP server support** | Load and manage Model Context Protocol servers from your Claude config |
| **Skill management** | View and manage Claude Code skills (Extensions page) |
| **Import CLI sessions** | Import existing sessions from the Claude Code CLI |
| **Multi-language UI** | English · 简体中文 · 繁體中文 |
| **Theme switching** | Light / Dark / System — persisted across restarts |
| **API provider config** | Add and manage multiple Anthropic API providers with custom base URLs |
| **Permission control** | Fine-grained tool permission modes with interactive approval dialogs |
| **Update notifications** | Automatic check for Claude Code CLI updates on startup |
| **Cross-platform** | Windows · macOS · Linux |

---

## 📋 Requirements

- **Python** 3.10 or later
- **Node.js** (for Claude Code CLI)
- **Claude Code CLI** — install via npm:
  ```bash
  npm install -g @anthropic-ai/claude-code
  ```
- **Anthropic API key** — set via environment variable or configured in the Settings page

---

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/knqiufan/Misaka.git
cd Misaka

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Set your API key (or configure it in Settings)
set ANTHROPIC_API_KEY=sk-ant-...   # Windows
export ANTHROPIC_API_KEY=sk-ant-... # macOS / Linux

# 4. Launch Misaka
misaka
# or
python -m misaka.main
```

The application window opens at **1280 × 860** (minimum 800 × 600). All data — sessions, settings, and logs — is stored in `~/.misaka/`.

---

## 🗂 Project Structure

```
Misaka/
├── misaka/
│   ├── main.py                 # Entry point & dependency injection
│   ├── config.py               # Paths, env vars, setting keys
│   ├── state.py                # Reactive application state
│   ├── db/                     # Database layer (SQLite / SeekDB)
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── sqlite_backend.py
│   │   └── seekdb_backend.py
│   ├── services/               # Business logic services
│   │   ├── claude_service.py   # Claude Agent SDK integration
│   │   ├── session_service.py
│   │   ├── message_service.py
│   │   ├── provider_service.py
│   │   ├── mcp_service.py
│   │   ├── settings_service.py
│   │   ├── permission_service.py
│   │   ├── skill_service.py
│   │   └── ...
│   ├── ui/
│   │   ├── app_shell.py        # Root layout shell
│   │   ├── theme.py            # Material Design 3 theming
│   │   ├── components/         # Reusable UI components
│   │   └── pages/              # Chat · Settings · Plugins · Extensions
│   └── i18n/                   # Locale files (en / zh_CN / zh_TW)
├── assets/                     # App icon
├── tests/                      # Unit & integration tests
├── docs/                       # Architecture & planning docs
├── pyproject.toml
└── requirements.txt
```

---

## ⚙️ Configuration

### API Key

Set the environment variable before launching, or add a provider in **Settings → API Providers**:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Data Directory

Override the default `~/.misaka/` storage location:

```bash
export MISAKA_DATA_DIR=/path/to/custom/dir
```

### MCP Servers

Misaka automatically reads MCP server configurations from:

- `~/.claude.json`
- `~/.claude/settings.json`

You can also manage servers directly from the **Plugins** page inside the app.

---

## 🛠 Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run tests
pytest

# Lint (Ruff)
ruff check misaka/

# Type check (mypy)
mypy misaka/
```

### Building a standalone executable

```bash
pip install -e ".[build]"
pyinstaller misaka.spec
```

---

## 🏗 Architecture

Misaka follows a clean layered architecture with dependency injection:

```
UI Layer  →  State  →  Services  →  Database / External APIs
```

- **`ServiceContainer`** — instantiated once at startup, holds all service singletons
- **`AppState`** — reactive state object passed through the UI tree
- **`DatabaseBackend`** — pluggable backend (SQLite default, SeekDB optional)
- **`ClaudeService`** — wraps `claude-agent-sdk` for streaming, MCP, and permission handling

See [`docs/plans/2026-02-23-architecture-design.md`](docs/plans/2026-02-23-architecture-design.md) for the full design document.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `flet >= 0.27` | Cross-platform Flutter-based UI framework |
| `claude-agent-sdk >= 0.1.5` | Official Claude Code agent integration |
| `Pygments >= 2.18` | Syntax highlighting in code blocks |
| `watchdog >= 4.0` | File system event watching |
| `aiofiles >= 24.0` | Async file I/O |
| `anyio >= 4.0` | Async concurrency primitives |

---

## 📄 License

[MIT](LICENSE)
