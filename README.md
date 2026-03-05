# Misaka

[CN](README_CN.md) · [EN](README.md)

> A desktop GUI client for Claude Code, built with Python and [Flet](https://flet.dev).

Misaka brings the power of Claude Code to a polished native desktop experience — multi-turn streaming conversations, session management, file tree browsing, MCP server integration, and more, all wrapped in a clean Material Design 3 interface.

---

## 🌟 Why Misaka?

Misaka stands out with these **unique features**:

| Feature | Description |
|---------|-------------|
| **🔍 Environment Check** | On startup, automatically detects Claude Code CLI, Node.js, Python, and Git. Missing tools? One-click install with platform-specific commands (winget/brew/apt). |
| **📦 Version Check** | Checks for Claude Code CLI updates on startup. One-click upgrade via `npm install -g @anthropic-ai/claude-code@latest`. |
| **🔀 Claude Code Router** | Manage multiple API configurations (different providers, models, Agent Team mode). Switch instantly — writes to `~/.claude/settings.json`. No other GUI offers this. |
| **🖥️ Native Desktop** | Python + Flet (Flutter-based). Not a web app — runs as a true native window. |
| **🛡️ Permission Control** | Fine-grained tool permission modes with interactive approval dialogs before file edits or shell commands. |
| **📚 Skills Management** | View, create, edit, and refresh Claude Code Skills (Extensions) directly in the app. |

---

## ✨ Features

| Category | Details |
|---|---|
| **Multi-model chat** | Switch between Claude Sonnet, Opus, and Haiku via `/model` command |
| **Streaming responses** | Real-time token-by-token rendering with abort support and thinking animation |
| **Session management** | Create, rename, archive, delete, and search conversation sessions |
| **Three conversation modes** | `Code` · `Plan` · `Ask` — dropdown selector for Claude Code's native modes |
| **File tree browser** | Browse your project directory in the right panel with live file preview |
| **MCP server support** | Load and manage Model Context Protocol servers from your Claude config |
| **Skill management** | View, create, edit, and refresh Claude Code skills (Extensions page) |
| **Claude Code Router** | Multi-config system for managing different API providers and model presets |
| **Import CLI sessions** | Import existing sessions from the Claude Code CLI |
| **Multi-language UI** | English · 简体中文 · 繁體中文 |
| **Theme switching** | Light / Dark / System — persisted across restarts, customizable accent color |
| **API provider config** | Add and manage multiple Anthropic API providers with custom base URLs |
| **Permission control** | Fine-grained tool permission modes with interactive approval dialogs |
| **Update notifications** | Automatic check for Claude Code CLI updates on startup |
| **Cross-platform** | Windows · macOS · Linux |
| **Developer mode** | Hot reload and debug logging support for development |

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

## ⚙️ Configuration

### API Key

Set the environment variable before launching, or add a provider in **Settings → API Providers**:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Claude Code Router — Quick Guide

The **Claude Code Router** lets you manage multiple API configurations and switch between them instantly.

**1. Add a configuration**

- Go to **Settings → Claude Code Router**
- Click **Add Configuration**
- Fill in:
  - **Provider Name** — e.g. "Anthropic Official", "Custom API"
  - **API Key** — your Anthropic API key
  - **Request URL** — leave empty for default, or use a custom base URL
  - **Main / Haiku / Opus / Sonnet Model** — model IDs for each tier
  - **Agent Team Mode** — toggle for Agent Teams feature

**2. Enable a configuration**

- Click **Enable** on the config you want to use
- Misaka writes the config to `~/.claude/settings.json`
- Claude Code CLI will use this config for all sessions

**3. Use cases**

- Switch between official Anthropic API and third-party compatible endpoints
- Use different models per project (e.g. Haiku for quick tasks, Opus for complex coding)
- Separate configs for work vs personal API keys

### Third-Party Plugins (MCP Servers) — Quick Guide

MCP (Model Context Protocol) servers extend Claude Code with tools like databases, APIs, and file systems.

**Option A: Configure via Misaka UI**

1. Open **Plugins** (MCP Servers) from the sidebar
2. Click **Add Server**
3. Choose **Transport Type**:
   - **stdio** — local process (e.g. `npx -y @modelcontextprotocol/server-filesystem ~/Documents`)
   - **http** — remote HTTP endpoint (e.g. `https://mcp.notion.com/mcp`)
   - **sse** — legacy SSE endpoint
4. For **stdio**: enter **Command** and **Arguments** (space-separated)
5. For **http/sse**: enter **URL**
6. Click **Add** — config is saved to `~/.claude.json` or `~/.claude/settings.json`

**Option B: Configure via config files**

Edit `~/.claude.json` or `~/.claude/settings.json`:

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

Then click **Reload Config** in the Plugins page. See [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) for more examples.

### Data Directory

Override the default `~/.misaka/` storage location:

```bash
export MISAKA_DATA_DIR=/path/to/custom/dir
```

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

# Run with hot reload (dev mode)
python -m misaka.main
# Or use flet run
flet run -m misaka.main -d -r
```

### Building a standalone executable

```bash
pip install -e ".[build]"
pyinstaller misaka.spec
```

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
