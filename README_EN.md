<p align="center">
  <img src="./assets/icon.svg" alt="Misaka Logo" width="120" />
</p>

<h1 align="center">Misaka</h1>

<p align="center">
  <strong>Desktop GUI Client for Claude Code</strong><br>
  Unlock the full potential of Claude Code with a native desktop experience
</p>

<p align="center">
  <a href="https://github.com/knqiufan/Misaka/releases"><img src="https://img.shields.io/github/v/release/knqiufan/Misaka?style=flat-square&color=blue" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/knqiufan/Misaka?style=flat-square" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://flet.dev"><img src="https://img.shields.io/badge/Flet-0.27+-blue?style=flat-square" alt="Flet"></a>
  <a href="https://github.com/knqiufan/Misaka"><img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey?style=flat-square" alt="Platform"></a>
</p>

<p align="center">
  <a href="README.md">中文</a> · English
</p>

---

> **Fully open source — Stars and contributions welcome!** The project is under active development and we'd love your help.

## What is Misaka?

**Misaka** is a **desktop GUI client for Claude Code** built with Python + [Flet](https://flet.dev) (Flutter). It solves the problem of Claude Code being CLI-only by wrapping multi-turn streaming conversations, session management, file browsing, MCP server integration, a skill marketplace, and more into a polished Material Design 3 native desktop app.

**In one sentence:** Use Claude Code like you'd use VS Code — but lighter and more focused.

![主界面](./image/主界面.png)

---

## Why Misaka?

### Problems It Solves

- **No official GUI** — Claude Code only ships a CLI; Misaka gives it a full graphical interface
- **Painful config switching** — Manually editing config files to switch providers and models? Misaka's Router does it in one click
- **Complex initial setup** — Don't know where to start? The guided Setup Wizard detects and configures everything automatically
- **No runtime visibility** — Token usage, MCP server health, session stats — all visible at a glance on the Dashboard

### Unique Highlights

| Feature | Description |
|---------|-------------|
| **Claude Code Router** | Manage multiple API configs (different providers / models / Agent Team mode) and switch instantly — writes to `~/.claude/settings.json`. **No other GUI tool offers this.** |
| **Guided Setup Wizard** | First-launch walkthrough: CLI detection → API config → workspace selection. Zero-config onboarding. |
| **Provider Doctor** | One-click diagnostics for CLI installation, API key validity, and environment variables. Pinpoints issues with severity levels and fix suggestions. |
| **Unified Dashboard** | Environment status, MCP health, session stats, skill overview, cumulative token usage — full system visibility in one place. |
| **Online Skill Market** | Browse, search, and one-click install community skills from skills.sh. |
| **Thinking Visualization** | See the model's reasoning process in real-time with collapsible Thinking Blocks. |
| **Native Desktop App** | Flutter-rendered, not a web app — fast startup, low overhead, native experience. |

---

## Feature Overview

### Conversation & Interaction

- **Streaming responses** — Real-time token-by-token rendering with abort support
- **Three conversation modes** — `Code` · `Plan` · `Ask`, switchable via dropdown
- **Multi-model switching** — Switch between Sonnet, Opus, and Haiku via `/model`
- **Thinking Blocks** — Real-time display of model reasoning, collapsible for clean reading
- **Slash commands** — `/init`, `/doctor`, and more, sent directly from the input
- **Permission control** — Interactive approval dialogs before file edits or shell execution
- **Message copying** — Right-click to copy both user messages and AI replies

### Session Management

- **Create / rename / delete / search** sessions
- **Group by project** — Session list supports grouping by working directory or by date
- **Session archiving** — Archive sessions via right-click menu; restore anytime
- **Import CLI sessions** — One-click import from Claude Code CLI history with pagination and search

### Smart Diagnostics

- **Environment check** — Auto-detects Claude Code CLI, Node.js, Python, Git on startup; one-click install for missing tools
- **Version check** — Auto-detects CLI updates; one-click upgrade
- **Provider Doctor** — Structured diagnostic probes: CLI existence, API key validity, environment completeness. Severity-graded reports with fix suggestions
- **Structured error classifier** — 16 error categories (network / auth / rate-limit / parsing / permission / timeout, etc.) with user-friendly messages and suggested actions

### Data & Visualization

- **Unified Dashboard** — Environment status, MCP health, session stats, skill stats, cumulative token overview
- **Daily usage charts** — Per-day token aggregation with bar charts for input/output tokens
- **Context usage indicator** — Real-time token consumption and context window progress in the chat footer
- **Runtime logs** — In-memory ring buffer (200 entries) with auto-sanitization, viewable in Settings

### Extension Ecosystem

- **MCP server management** — Supports stdio / http / sse transport types; add via UI or config files
- **Project-level MCP config** — Auto-loads `.mcp.json` from the project directory for per-project isolation
- **Skill management** — Browse skills from four sources: Global / Project / Installed / Plugin
- **Online skill market** — Search and install community skills from skills.sh
- **Skill editor** — Two-pane layout: SKILL.md editor on the left, folder browser on the right

### Personalization

- **Multi-language** — English · 简体中文 · 繁體中文
- **Theme switching** — Light / Dark / System, with customizable accent color
- **Custom data directory** — Set via `MISAKA_DATA_DIR` environment variable

---

## Screenshots

<details>
<summary>Click to expand screenshots</summary>

**Claude Code Router Configuration**

![Router](./image/Router.png)

**MCP Server Management**

![MCP](./image/MCP.png)

**Skill Management**

![Skills](./image/Skill本地.png)

![Skills](./image/Skill市场.png)

**instrument panel**

![仪表盘](./image/仪表盘.png)

</details>

---

## Quick Start

### Requirements

| Dependency | Requirement |
|------------|-------------|
| Python | 3.10+ |
| Node.js | Required for Claude Code CLI |
| Claude Code CLI | `npm install -g @anthropic-ai/claude-code` |
| API Key | Anthropic API key (env var or in-app config) |

### Install & Run

```bash
# Clone the repository
git clone https://github.com/knqiufan/Misaka.git
cd Misaka

# Install dependencies
pip install -e ".[dev]"

# Set your API key (or configure in Settings)
set ANTHROPIC_API_KEY=sk-ant-...    # Windows
export ANTHROPIC_API_KEY=sk-ant-... # macOS / Linux

# Launch
misaka
# or
python -m misaka.main
```

The app window opens at **1280 × 860** (minimum 800 × 600). All data is stored in `~/.misaka/`.

---

## Configuration

### Claude Code Router

Manage multiple API configurations and switch between them instantly — no manual file editing.

1. Go to **Settings → Claude Code Router** → click **Add Configuration**
2. Fill in provider name, API key, base URL, and model IDs
3. Click **Enable** — config is written to `~/.claude/settings.json` automatically

**Use cases:**
- Switch between official Anthropic API and third-party compatible endpoints
- Different models for different projects (Haiku for quick tasks, Opus for complex coding)
- Separate work and personal API keys

### MCP Servers

**Option A: Via UI** — Sidebar → Plugins → Add Server → choose transport type (stdio / http / sse)

**Option B: Via config files** — Edit `~/.claude.json` or `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    },
    "notion": {
      "type": "http",
      "url": "https://mcp.notion.com/mcp"
    }
  }
}
```

**Project-level config** — Place a `.mcp.json` in your project root; Misaka loads it automatically.

### Data Directory

```bash
export MISAKA_DATA_DIR=/path/to/custom/dir
```

---

## Tech Stack

| Category | Technology |
|----------|------------|
| **Language** | Python 3.10+ |
| **UI Framework** | [Flet](https://flet.dev) (Flutter-based) |
| **Claude Integration** | [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) |
| **Charts** | flet-charts |
| **Syntax Highlighting** | Pygments |
| **Image Handling** | Pillow |
| **File Watching** | watchdog |
| **Async I/O** | aiofiles · anyio |

### Architecture

```
User Action → Flet UI Layer → AppState (single source of truth) → ServiceContainer → Database / Claude SDK
```

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check misaka/

# Type check
mypy misaka/

# Hot reload dev mode
flet run -m misaka.main -d -r
```

### Building

```bash
pip install -e ".[build]"
pyinstaller misaka.spec
```

---

## About the Name

**Misaka** (御坂) — a tribute to *A Certain Scientific Railgun*. The name evokes the Misaka Network's powerful computing and connectivity.

---

## Contributing

Issues and Pull Requests are welcome! The project is under active development and your participation is greatly appreciated.

## License

[Apache License 2.0](LICENSE)
