# Misaka-py New Features Implementation Plan

**Date:** 2026-02-23
**Status:** Active
**Author:** Architect Agent

---

## Table of Contents

1. [Overview](#1-overview)
2. [Feature 1: Environment Check & One-Click Install](#2-feature-1-environment-check--one-click-install)
3. [Feature 2: Claude Code Update Detection](#3-feature-2-claude-code-update-detection)
4. [Feature 3: i18n - Language Internationalization](#4-feature-3-i18n---language-internationalization)
5. [File-by-File Task Breakdown](#5-file-by-file-task-breakdown)
6. [Flet 0.80.x Compatibility Notes](#6-flet-080x-compatibility-notes)
7. [Testing Plan](#7-testing-plan)

---

## 1. Overview

### 1.1 Scope

Three features to implement in the Misaka-py Flet desktop application:

| # | Feature | Complexity | New Files | Modified Files |
|---|---------|-----------|-----------|---------------|
| 1 | Environment Check & One-Click Install | High | 3 | 4 |
| 2 | Claude Code Update Detection | Medium | 2 | 3 |
| 3 | i18n - Language Internationalization | High | 6 | ~15 |

### 1.2 Architecture Principles

- **Services layer**: All new business logic goes into `misaka/services/`. Services are stateless (or hold minimal state) and receive the `DatabaseBackend` via constructor injection.
- **State management**: New reactive state fields go on `AppState` in `misaka/state.py`. UI components read from state; services mutate it.
- **UI components**: New Flet controls go into `misaka/ui/components/`. Pages go into `misaka/ui/pages/`.
- **Configuration**: New setting keys go into `misaka/config.py::SettingKeys`.
- **Cross-platform**: All subprocess calls must handle Windows (.cmd/.bat wrappers, `shell=True`), macOS (Homebrew paths), and Linux (apt/dnf/snap).

### 1.3 Dependency on Existing Code

The three features integrate with:

- `misaka/main.py` - `ServiceContainer` gets new services; startup hook for environment check
- `misaka/state.py` - `AppState` gets new fields for env check results, update status, locale
- `misaka/config.py` - New `SettingKeys` for language preference
- `misaka/utils/platform.py` - Already has `find_claude_binary()`, `get_claude_version()` -- reused by all three features
- `misaka/ui/app_shell.py` - Wires environment check dialog on startup
- `misaka/ui/pages/settings_page.py` - Gets a language selector section

---

## 2. Feature 1: Environment Check & One-Click Install

### 2.1 Requirements

On startup, check if the following tools are installed locally:
- **Claude Code CLI** (`claude --version`)
- **Node.js** (`node --version`)
- **Python** (`python3 --version` / `python --version`)
- **Git** (`git --version`)

If any are missing, show a dialog with status indicators and one-click install buttons. Must support Windows, macOS, and Linux.

### 2.2 Data Model

```python
# misaka/services/env_check_service.py

@dataclass
class ToolStatus:
    """Status of a single tool dependency."""
    name: str              # "Claude Code CLI", "Node.js", "Python", "Git"
    command: str           # "claude", "node", "python3", "git"
    version: str | None    # "1.2.3" or None if not found
    is_installed: bool     # True if binary found and responds to --version
    install_url: str       # URL for manual download
    install_command: str   # Platform-specific install command


@dataclass
class EnvironmentCheckResult:
    """Aggregated result of all environment checks."""
    tools: list[ToolStatus]
    all_installed: bool    # True if every tool is installed
    checked_at: str        # ISO timestamp
```

### 2.3 Backend: `misaka/services/env_check_service.py` (NEW)

```python
class EnvCheckService:
    """Service for checking and installing development tool dependencies."""

    async def check_all(self) -> EnvironmentCheckResult:
        """Run all environment checks concurrently.

        Uses asyncio.gather to check all tools in parallel.
        Returns an EnvironmentCheckResult with status for each tool.
        """

    async def check_tool(self, command: str, version_flag: str = "--version") -> ToolStatus:
        """Check a single tool by running `command version_flag`.

        Handles Windows .cmd/.bat wrappers, expanded PATH lookup.
        Parses version string from stdout.
        """

    async def install_tool(
        self,
        tool_name: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> bool:
        """Install a tool via platform-appropriate method.

        Returns True on success, False on failure.
        Calls on_progress with status messages during install.
        """

    def _get_install_info(self, tool_name: str) -> tuple[str, str]:
        """Return (install_command, install_url) for the given tool.

        Platform-specific logic:
        - Windows: winget, choco, or direct download URL
        - macOS: brew install, or direct download URL
        - Linux: apt/dnf/snap, or direct download URL
        """
```

**Tool detection logic:**

| Tool | Binary | Version flag | Windows | macOS | Linux |
|------|--------|-------------|---------|-------|-------|
| Claude Code CLI | `claude` | `--version` | Check npm global, `%APPDATA%/npm` | Check `/usr/local/bin`, `/opt/homebrew/bin` | Check `~/.local/bin`, npm global |
| Node.js | `node` | `--version` | `shutil.which("node")` | `shutil.which("node")` | `shutil.which("node")` |
| Python | `python3` / `python` | `--version` | Try `python`, then `python3` | Try `python3`, then `python` | Try `python3`, then `python` |
| Git | `git` | `--version` | `shutil.which("git")` | `shutil.which("git")` | `shutil.which("git")` |

**Install methods per platform:**

| Tool | Windows | macOS | Linux |
|------|---------|-------|-------|
| Claude Code | `npm install -g @anthropic-ai/claude-code` | `npm install -g @anthropic-ai/claude-code` | `npm install -g @anthropic-ai/claude-code` |
| Node.js | `winget install OpenJS.NodeJS.LTS` or download URL | `brew install node` or download URL | `curl -fsSL https://deb.nodesource.com/setup_lts.x \| sudo bash - && sudo apt install -y nodejs` |
| Python | `winget install Python.Python.3.12` or download URL | `brew install python@3.12` or download URL | `sudo apt install -y python3` |
| Git | `winget install Git.Git` or download URL | `brew install git` or download URL | `sudo apt install -y git` |

**Important implementation details:**

- Use `shutil.which()` with `misaka.config.get_expanded_path()` for binary discovery
- For Claude CLI, reuse existing `misaka.utils.platform.find_claude_binary()`
- Run subprocess commands asynchronously using `asyncio.create_subprocess_exec()`
- Parse version from stdout using regex: `r"v?(\d+\.\d+(?:\.\d+)?)"`
- The install commands that require elevated privileges (sudo on Linux) should open a terminal emulator or use `pkexec`/`gsudo` -- but the primary path is `npm install -g` for Claude (no sudo needed if npm prefix is user-local) and download URLs for Node/Python/Git
- After installation, call `misaka.utils.platform.clear_claude_cache()` to invalidate the cached binary path

### 2.4 Frontend: `misaka/ui/components/env_check_dialog.py` (NEW)

```python
class EnvCheckDialog(ft.Column):
    """Full-screen overlay dialog showing environment check results.

    Displayed on startup if any required tools are missing.
    Shows a card per tool with status icon, version, and install button.
    """

    def __init__(
        self,
        state: AppState,
        check_result: EnvironmentCheckResult,
        on_install: Callable[[str], None] | None = None,
        on_dismiss: Callable[[], None] | None = None,
    ) -> None:
        ...

    def _build_tool_card(self, tool: ToolStatus) -> ft.Control:
        """Build a card for one tool.

        Shows:
        - Green check / red X icon
        - Tool name and version (or "Not installed")
        - "Install" button (if not installed) or "Installed" badge
        - Progress indicator during install

        Flet 0.80.x: Buttons use `content=` parameter.
        """

    def _build_install_button(self, tool: ToolStatus) -> ft.Control:
        """Build the install action area.

        Primary: One-click install button (runs install_command)
        Secondary: "Download" link (opens install_url in browser)
        """

    def refresh(self, check_result: EnvironmentCheckResult) -> None:
        """Update the dialog after an install attempt."""
```

**UI layout:**

```
+--------------------------------------------------+
|  Environment Setup                          [X]  |
|                                                   |
|  Misaka requires the following tools:          |
|                                                   |
|  [V] Claude Code CLI     v1.0.25    [Installed]  |
|  [V] Node.js             v20.11.1   [Installed]  |
|  [X] Python              Not found  [Install]    |
|  [V] Git                 v2.43.0    [Installed]  |
|                                                   |
|  [Skip]                         [Check Again]    |
+--------------------------------------------------+
```

### 2.5 Integration Points

**`misaka/state.py`** -- Add to `AppState.__init__`:
```python
# --- Environment check state ---
self.env_check_result: EnvironmentCheckResult | None = None
self.env_check_loading: bool = False
self.show_env_check_dialog: bool = False
```

**`misaka/main.py`** -- Add to `ServiceContainer.__init__`:
```python
from misaka.services.env_check_service import EnvCheckService
self.env_check_service = EnvCheckService()
```

**`misaka/main.py`** -- Add to `_main()` after UI build:
```python
# --- Run environment check on startup ---
async def _run_env_check():
    result = await services.env_check_service.check_all()
    state.env_check_result = result
    if not result.all_installed:
        state.show_env_check_dialog = True
    state.update()

page.run_task(_run_env_check)
```

**`misaka/ui/app_shell.py`** -- Add env check dialog overlay:
```python
from misaka.ui.components.env_check_dialog import EnvCheckDialog
# In _build_ui(), add the dialog as a Stack layer on top of the main content
```

### 2.6 Sequence Diagram

```
App Start
    |
    v
_main() -> ServiceContainer created
    |
    v
AppShell built, page.add(app_shell)
    |
    v
page.run_task(_run_env_check)
    |
    v
EnvCheckService.check_all()
    |-- asyncio.gather(check_tool("claude"), check_tool("node"), ...)
    |
    v
EnvironmentCheckResult -> state.env_check_result
    |
    v
If not all_installed -> show EnvCheckDialog overlay
    |
    v
User clicks "Install" -> EnvCheckService.install_tool(name)
    |-- Runs platform install command async
    |-- on_progress -> update UI progress
    |
    v
Recheck -> EnvCheckService.check_all() -> refresh dialog
    |
    v
User clicks "Skip" or all installed -> dismiss dialog
```

---

## 3. Feature 2: Claude Code Update Detection

### 3.1 Requirements

Detect if a newer version of Claude Code CLI is available. Show a notification bar to the user. The user can dismiss or click to update.

### 3.2 Data Model

```python
# misaka/services/update_check_service.py

@dataclass
class UpdateCheckResult:
    """Result of checking for Claude Code CLI updates."""
    current_version: str | None   # Currently installed version
    latest_version: str | None    # Latest version from npm registry
    update_available: bool        # True if latest > current
    checked_at: str               # ISO timestamp
```

### 3.3 Backend: `misaka/services/update_check_service.py` (NEW)

```python
class UpdateCheckService:
    """Service for detecting Claude Code CLI updates."""

    async def check_for_update(self) -> UpdateCheckResult:
        """Check if a newer version of Claude Code CLI is available.

        Steps:
        1. Get current version via `claude --version` (reuse platform.get_claude_version)
        2. Get latest version from npm registry API
        3. Compare using simple version tuple comparison
        """

    async def _get_latest_npm_version(self, package_name: str) -> str | None:
        """Fetch the latest version of an npm package from the registry.

        Uses `npm view @anthropic-ai/claude-code version` subprocess call.
        Falls back to HTTPS request to registry.npmjs.org if npm is unavailable.
        """

    async def perform_update(
        self,
        on_progress: Callable[[str], None] | None = None,
    ) -> bool:
        """Update Claude Code CLI to the latest version.

        Runs: npm install -g @anthropic-ai/claude-code@latest
        Returns True on success.
        After update, clears the cached claude binary path.
        """

    @staticmethod
    def _compare_versions(current: str, latest: str) -> bool:
        """Return True if latest > current using tuple comparison.

        Parses "x.y.z" -> (x, y, z) and compares.
        """
```

**npm registry lookup strategies (in order):**

1. `npm view @anthropic-ai/claude-code version` -- Most reliable, uses user's npm config (proxy, registry override)
2. HTTP GET `https://registry.npmjs.org/@anthropic-ai/claude-code/latest` -- Fallback if npm CLI is not available, parse `version` field from JSON response

**Version comparison:**
- Parse version strings into `tuple[int, ...]` using `re.match(r"(\d+)\.(\d+)\.(\d+)")`
- Compare tuples lexicographically

### 3.4 Frontend: `misaka/ui/components/update_banner.py` (NEW)

```python
class UpdateBanner(ft.Container):
    """Notification banner shown when a Claude Code update is available.

    Appears at the top of the chat view (below the header bar).
    Dismissable with an X button.
    """

    def __init__(
        self,
        state: AppState,
        on_update: Callable[[], None] | None = None,
        on_dismiss: Callable[[], None] | None = None,
    ) -> None:
        ...

    def _build_ui(self) -> None:
        """Build the banner layout.

        Layout:
        [info-icon] Claude Code v1.1.0 is available (current: v1.0.25)  [Update] [X]

        Flet 0.80.x: Use content= for buttons.
        """

    def refresh(self) -> None:
        """Update visibility and content based on state."""
```

**UI layout:**

```
+------------------------------------------------------------------------+
| [i] Claude Code v1.1.0 available (current: v1.0.25)  [Update Now] [X] |
+------------------------------------------------------------------------+
```

### 3.5 Integration Points

**`misaka/state.py`** -- Add to `AppState.__init__`:
```python
# --- Update check state ---
self.update_check_result: UpdateCheckResult | None = None
self.update_dismissed: bool = False
self.update_in_progress: bool = False
```

**`misaka/main.py`** -- Add to `ServiceContainer.__init__`:
```python
from misaka.services.update_check_service import UpdateCheckService
self.update_check_service = UpdateCheckService()
```

**`misaka/main.py`** -- Add to `_main()` after env check:
```python
# --- Check for Claude Code updates ---
async def _run_update_check():
    result = await services.update_check_service.check_for_update()
    state.update_check_result = result
    state.update()

page.run_task(_run_update_check)
```

**`misaka/ui/components/chat_view.py`** -- Insert `UpdateBanner` between the header and the error banner:
```python
from misaka.ui.components.update_banner import UpdateBanner
# In _build_ui(), after header, before error_banner:
self._update_banner = UpdateBanner(
    state=self.state,
    on_update=self._handle_update,
    on_dismiss=self._dismiss_update,
)
```

### 3.6 Sequence Diagram

```
App Start (after env check completes)
    |
    v
page.run_task(_run_update_check)
    |
    v
UpdateCheckService.check_for_update()
    |-- get_claude_version(claude_path) -> "1.0.25"
    |-- _get_latest_npm_version("@anthropic-ai/claude-code") -> "1.1.0"
    |-- _compare_versions("1.0.25", "1.1.0") -> True
    |
    v
UpdateCheckResult(update_available=True) -> state.update_check_result
    |
    v
ChatView._build_ui() sees update_available -> shows UpdateBanner
    |
    v
User clicks "Update Now" -> UpdateCheckService.perform_update()
    |-- Runs `npm install -g @anthropic-ai/claude-code@latest`
    |-- clear_claude_cache()
    |-- Recheck version
    |
    v
Banner updates to "Updated to v1.1.0" or shows error
```

---

## 4. Feature 3: i18n - Language Internationalization

### 4.1 Requirements

Support 3 languages:
- **Simplified Chinese** (`zh-CN`) -- default
- **Traditional Chinese** (`zh-TW`)
- **English** (`en`)

All user-facing strings in the UI must be translatable. The user selects their language in Settings; the choice persists across restarts.

### 4.2 Architecture: JSON-based Translation Files

Use a simple JSON file approach (no heavy i18n library dependency):

```
misaka/
  i18n/
    __init__.py          # Translation manager singleton
    en.json              # English strings
    zh_CN.json           # Simplified Chinese strings
    zh_TW.json           # Traditional Chinese strings
```

### 4.3 Backend: `misaka/i18n/__init__.py` (NEW)

```python
"""
Internationalization (i18n) module for Misaka.

Provides a simple, synchronous translation lookup system.
Translation files are JSON dictionaries with dotted key paths.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Supported locales
SUPPORTED_LOCALES = ("en", "zh-CN", "zh-TW")
DEFAULT_LOCALE = "zh-CN"

# Module-level singleton
_current_locale: str = DEFAULT_LOCALE
_translations: dict[str, dict[str, str]] = {}
_fallback_translations: dict[str, str] = {}


def init(locale: str = DEFAULT_LOCALE) -> None:
    """Initialize the i18n system by loading translation files.

    Should be called once at startup, after reading the user's
    language preference from settings.

    Args:
        locale: The locale code to use ("en", "zh-CN", "zh-TW").
    """
    global _current_locale, _translations, _fallback_translations
    _current_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE

    i18n_dir = Path(__file__).parent

    # Load all locale files
    for loc in SUPPORTED_LOCALES:
        file_name = loc.replace("-", "_") + ".json"  # "zh-CN" -> "zh_CN.json"
        file_path = i18n_dir / file_name
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _translations[loc] = _flatten_dict(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load i18n file %s: %s", file_path, exc)
                _translations[loc] = {}
        else:
            _translations[loc] = {}

    # Set fallback to English
    _fallback_translations = _translations.get("en", {})


def set_locale(locale: str) -> None:
    """Change the current locale at runtime.

    Does NOT reload files; assumes init() was already called.
    """
    global _current_locale
    if locale in SUPPORTED_LOCALES:
        _current_locale = locale


def get_locale() -> str:
    """Return the current locale code."""
    return _current_locale


def t(key: str, **kwargs: Any) -> str:
    """Translate a key to the current locale.

    Supports placeholder substitution: t("hello", name="World") ->
    "Hello, {name}" becomes "Hello, World"

    Falls back to English if key not found in current locale.
    Falls back to the key itself if not found in any locale.

    Args:
        key: Dotted key path, e.g. "nav.chat", "settings.title"
        **kwargs: Placeholder values for string formatting
    """
    translations = _translations.get(_current_locale, {})
    text = translations.get(key) or _fallback_translations.get(key) or key

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


def _flatten_dict(d: dict, prefix: str = "") -> dict[str, str]:
    """Flatten a nested dict into dotted key paths.

    {"nav": {"chat": "Chat"}} -> {"nav.chat": "Chat"}
    """
    result: dict[str, str] = {}
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_dict(v, full_key))
        else:
            result[full_key] = str(v)
    return result
```

### 4.4 Translation File Structure

**`misaka/i18n/en.json`:**
```json
{
  "app": {
    "name": "Misaka",
    "welcome_title": "Welcome to Misaka",
    "welcome_subtitle": "Select a chat session or create a new one to begin."
  },
  "nav": {
    "chat": "Chat",
    "settings": "Settings",
    "plugins": "Plugins",
    "extensions": "Extensions"
  },
  "chat": {
    "new_chat": "New Chat",
    "delete": "Delete",
    "rename": "Rename",
    "archive": "Archive",
    "clear_messages": "Clear messages",
    "send": "Send",
    "stop": "Stop",
    "toggle_left_panel": "Toggle left panel",
    "toggle_right_panel": "Toggle right panel",
    "no_sessions": "No chat sessions yet",
    "type_message": "Type a message..."
  },
  "settings": {
    "title": "Settings",
    "api_providers": "API Providers",
    "api_providers_desc": "Configure API providers for Claude Code. The active provider will be used for all queries.",
    "add_provider": "Add Provider",
    "edit_provider": "Edit Provider",
    "no_providers": "No providers configured. Add one to get started.",
    "provider_name": "Name",
    "provider_type": "Provider Type",
    "api_key": "API Key",
    "base_url": "Base URL (optional)",
    "extra_env": "Extra Environment Variables (JSON)",
    "notes": "Notes",
    "save": "Save",
    "cancel": "Cancel",
    "active": "ACTIVE",
    "inactive": "INACTIVE",
    "activate": "Activate",
    "deactivate": "Deactivate",
    "delete": "Delete",
    "edit": "Edit",
    "appearance": "Appearance",
    "appearance_desc": "Choose your preferred theme.",
    "theme_system": "System",
    "theme_light": "Light",
    "theme_dark": "Dark",
    "permission_mode": "Permission Mode",
    "permission_mode_desc": "Control how Misaka handles tool permission requests.",
    "perm_default": "Default",
    "perm_default_desc": "Ask for dangerous operations",
    "perm_accept_edits": "Accept Edits",
    "perm_accept_edits_desc": "Auto-approve file edits",
    "perm_bypass": "Bypass All",
    "perm_bypass_desc": "No permission prompts (use with caution)",
    "claude_code": "Claude Code",
    "claude_code_desc": "Configure defaults for Claude Code CLI integration.",
    "default_working_dir": "Default Working Directory",
    "default_model": "Default Model",
    "language": "Language",
    "language_desc": "Choose your preferred display language.",
    "about": "About",
    "about_desc": "Built with Flet + Python"
  },
  "plugins": {
    "title": "Plugins (MCP Servers)",
    "description": "Manage MCP (Model Context Protocol) servers that extend Claude's capabilities.",
    "add_server": "Add Server",
    "no_servers": "No MCP servers configured",
    "no_servers_hint": "Add a server or configure them in ~/.claude.json",
    "server_name": "Server Name",
    "transport_type": "Transport Type",
    "command": "Command (for stdio)",
    "arguments": "Arguments (space-separated)",
    "url": "URL (for sse/http)",
    "add": "Add",
    "remove": "Remove",
    "reload_config": "Reload Config",
    "config_files": "Configuration Files",
    "config_files_desc": "MCP servers can be configured in:\n  ~/.claude.json (mcpServers section)\n  ~/.claude/settings.json"
  },
  "extensions": {
    "title": "Extensions",
    "description": "Manage custom skills and extensions that enhance Misaka's capabilities.",
    "coming_soon": "Extensions Coming Soon",
    "coming_soon_desc": "Custom skills and extensions will allow you to add\npersonalized commands and workflows to Misaka.",
    "planned_features": "Planned Features",
    "custom_skills": "Custom Skills",
    "custom_skills_desc": "Define reusable prompt templates and workflows",
    "import_export": "Import/Export",
    "import_export_desc": "Share skills with the community",
    "skill_editor": "Skill Editor",
    "skill_editor_desc": "Visual editor for creating and testing skills",
    "keyboard_shortcuts": "Keyboard Shortcuts",
    "keyboard_shortcuts_desc": "Bind skills to custom keyboard shortcuts"
  },
  "env_check": {
    "title": "Environment Setup",
    "description": "Misaka requires the following tools:",
    "installed": "Installed",
    "not_installed": "Not installed",
    "install": "Install",
    "installing": "Installing...",
    "install_failed": "Install failed",
    "download": "Download",
    "skip": "Skip",
    "check_again": "Check Again",
    "all_ready": "All tools are installed! You're ready to go.",
    "claude_cli": "Claude Code CLI",
    "nodejs": "Node.js",
    "python": "Python",
    "git": "Git"
  },
  "update": {
    "available": "Claude Code {version} is available (current: {current})",
    "update_now": "Update Now",
    "updating": "Updating...",
    "updated": "Updated to {version}",
    "update_failed": "Update failed: {error}",
    "dismiss": "Dismiss"
  },
  "common": {
    "ok": "OK",
    "cancel": "Cancel",
    "save": "Save",
    "delete": "Delete",
    "edit": "Edit",
    "close": "Close",
    "loading": "Loading...",
    "error": "Error",
    "success": "Success",
    "no_key": "No key",
    "default_url": "Default URL"
  }
}
```

**`misaka/i18n/zh_CN.json`:** (Same structure, Simplified Chinese values)
```json
{
  "app": {
    "name": "Misaka",
    "welcome_title": "欢迎使用 Misaka",
    "welcome_subtitle": "选择一个聊天会话或创建一个新会话开始使用。"
  },
  "nav": {
    "chat": "聊天",
    "settings": "设置",
    "plugins": "插件",
    "extensions": "扩展"
  },
  "chat": {
    "new_chat": "新建聊天",
    "delete": "删除",
    "rename": "重命名",
    "archive": "归档",
    "clear_messages": "清空消息",
    "send": "发送",
    "stop": "停止",
    "toggle_left_panel": "切换左侧面板",
    "toggle_right_panel": "切换右侧面板",
    "no_sessions": "还没有聊天会话",
    "type_message": "输入消息..."
  },
  "settings": {
    "title": "设置",
    "api_providers": "API 提供商",
    "api_providers_desc": "配置 Claude Code 的 API 提供商。激活的提供商将用于所有查询。",
    "add_provider": "添加提供商",
    "edit_provider": "编辑提供商",
    "no_providers": "未配置提供商，请添加一个以开始使用。",
    "provider_name": "名称",
    "provider_type": "提供商类型",
    "api_key": "API 密钥",
    "base_url": "基础 URL（可选）",
    "extra_env": "额外环境变量（JSON）",
    "notes": "备注",
    "save": "保存",
    "cancel": "取消",
    "active": "已激活",
    "inactive": "未激活",
    "activate": "激活",
    "deactivate": "停用",
    "delete": "删除",
    "edit": "编辑",
    "appearance": "外观",
    "appearance_desc": "选择您喜欢的主题。",
    "theme_system": "跟随系统",
    "theme_light": "浅色",
    "theme_dark": "深色",
    "permission_mode": "权限模式",
    "permission_mode_desc": "控制 Misaka 如何处理工具权限请求。",
    "perm_default": "默认",
    "perm_default_desc": "危险操作时询问",
    "perm_accept_edits": "接受编辑",
    "perm_accept_edits_desc": "自动批准文件编辑",
    "perm_bypass": "跳过所有",
    "perm_bypass_desc": "不提示权限（请谨慎使用）",
    "claude_code": "Claude Code",
    "claude_code_desc": "配置 Claude Code CLI 集成的默认设置。",
    "default_working_dir": "默认工作目录",
    "default_model": "默认模型",
    "language": "语言",
    "language_desc": "选择界面显示语言。",
    "about": "关于",
    "about_desc": "基于 Flet + Python 构建"
  },
  "plugins": {
    "title": "插件（MCP 服务器）",
    "description": "管理扩展 Claude 能力的 MCP（模型上下文协议）服务器。",
    "add_server": "添加服务器",
    "no_servers": "未配置 MCP 服务器",
    "no_servers_hint": "添加服务器或在 ~/.claude.json 中配置",
    "server_name": "服务器名称",
    "transport_type": "传输类型",
    "command": "命令（用于 stdio）",
    "arguments": "参数（空格分隔）",
    "url": "URL（用于 sse/http）",
    "add": "添加",
    "remove": "移除",
    "reload_config": "重新加载配置",
    "config_files": "配置文件",
    "config_files_desc": "MCP 服务器可以在以下位置配置：\n  ~/.claude.json（mcpServers 部分）\n  ~/.claude/settings.json"
  },
  "extensions": {
    "title": "扩展",
    "description": "管理增强 Misaka 功能的自定义技能和扩展。",
    "coming_soon": "扩展功能即将推出",
    "coming_soon_desc": "自定义技能和扩展将允许您为 Misaka\n添加个性化的命令和工作流。",
    "planned_features": "规划中的功能",
    "custom_skills": "自定义技能",
    "custom_skills_desc": "定义可重用的提示模板和工作流",
    "import_export": "导入/导出",
    "import_export_desc": "与社区分享技能",
    "skill_editor": "技能编辑器",
    "skill_editor_desc": "用于创建和测试技能的可视化编辑器",
    "keyboard_shortcuts": "快捷键",
    "keyboard_shortcuts_desc": "将技能绑定到自定义快捷键"
  },
  "env_check": {
    "title": "环境检查",
    "description": "Misaka 需要以下工具：",
    "installed": "已安装",
    "not_installed": "未安装",
    "install": "安装",
    "installing": "安装中...",
    "install_failed": "安装失败",
    "download": "下载",
    "skip": "跳过",
    "check_again": "重新检查",
    "all_ready": "所有工具已安装！准备就绪。",
    "claude_cli": "Claude Code CLI",
    "nodejs": "Node.js",
    "python": "Python",
    "git": "Git"
  },
  "update": {
    "available": "Claude Code {version} 已可用（当前版本：{current}）",
    "update_now": "立即更新",
    "updating": "更新中...",
    "updated": "已更新到 {version}",
    "update_failed": "更新失败：{error}",
    "dismiss": "忽略"
  },
  "common": {
    "ok": "确定",
    "cancel": "取消",
    "save": "保存",
    "delete": "删除",
    "edit": "编辑",
    "close": "关闭",
    "loading": "加载中...",
    "error": "错误",
    "success": "成功",
    "no_key": "未设置密钥",
    "default_url": "默认 URL"
  }
}
```

**`misaka/i18n/zh_TW.json`:** (Same structure, Traditional Chinese values -- same keys, Traditional Chinese characters)

### 4.5 Integration Points

**`misaka/config.py`** -- Add to `SettingKeys`:
```python
LANGUAGE = "language"
```

**`misaka/state.py`** -- Add to `AppState.__init__`:
```python
# --- i18n state ---
self.locale: str = "zh-CN"  # Current locale
```

**`misaka/main.py`** -- Add to `_main()` before building UI:
```python
import misaka.i18n as i18n

# Load saved language preference
saved_lang = services.settings_service.get(SettingKeys.LANGUAGE)
locale = saved_lang if saved_lang in i18n.SUPPORTED_LOCALES else i18n.DEFAULT_LOCALE
i18n.init(locale)
state.locale = locale
```

**`misaka/ui/pages/settings_page.py`** -- Add language selector section:
```python
# New section: _build_language_section()
# Shows a radio group or segmented button with 3 options:
# - 简体中文 (zh-CN)
# - 繁體中文 (zh-TW)
# - English (en)
#
# On change:
# 1. Save to settings: db.set_setting("language", locale)
# 2. Update state: state.locale = locale
# 3. Update i18n: i18n.set_locale(locale)
# 4. Rebuild all UI: state.update()
```

### 4.6 i18n Usage Pattern in UI Components

All UI components replace hardcoded strings with `t()` calls:

```python
from misaka.i18n import t

# Before:
ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD)

# After:
ft.Text(t("settings.title"), size=24, weight=ft.FontWeight.BOLD)
```

**Files that need string replacement:**

| File | Approximate string count |
|------|------------------------|
| `misaka/ui/components/nav_rail.py` | 4 (Chat, Settings, Plugins, Extensions) |
| `misaka/ui/components/chat_view.py` | ~10 (Welcome, tooltips, labels) |
| `misaka/ui/components/chat_list.py` | ~5 (New Chat, Delete, Rename, etc.) |
| `misaka/ui/components/message_input.py` | ~3 (placeholder, send, stop) |
| `misaka/ui/components/right_panel.py` | ~5 (Files, Tasks, tab labels) |
| `misaka/ui/components/task_list.py` | ~4 (task statuses) |
| `misaka/ui/components/permission_dialog.py` | ~4 (Allow, Deny, descriptions) |
| `misaka/ui/components/connection_status.py` | ~2 (Connected, Disconnected) |
| `misaka/ui/pages/settings_page.py` | ~30 (all section titles, labels, descriptions) |
| `misaka/ui/pages/plugins_page.py` | ~15 (titles, descriptions, labels) |
| `misaka/ui/pages/extensions_page.py` | ~12 (titles, descriptions, feature items) |
| `misaka/ui/pages/chat_page.py` | ~2 (indirect via components) |
| `misaka/ui/app_shell.py` | 0 (uses nav_rail which handles its own strings) |
| `misaka/ui/components/env_check_dialog.py` | ~10 (new file, use t() from start) |
| `misaka/ui/components/update_banner.py` | ~5 (new file, use t() from start) |

### 4.7 Language Switching: Full Rebuild Strategy

When the user changes language:

1. `settings_page._change_language(locale)` is called
2. Persist: `db.set_setting("language", locale)`
3. Update i18n: `i18n.set_locale(locale)`
4. Update state: `state.locale = locale`
5. Rebuild the entire UI: `app_shell._rebuild_all_pages()`

This requires `AppShell` to expose a method that recreates all page instances and resets the content area. Since Flet pages are regular Python objects, we can simply re-instantiate them.

```python
# misaka/ui/app_shell.py -- add method:
def rebuild_for_locale_change(self) -> None:
    """Rebuild all pages after a locale change."""
    self._build_pages()
    current_page = self._get_current_page()
    if self._content_area:
        self._content_area.content = current_page
    # Rebuild nav rail (labels change with locale)
    self._nav_rail = build_nav_rail(
        state=self.state,
        on_change=self._on_nav_change,
        on_theme_toggle=self._on_theme_toggle,
    )
    self.controls[0] = self._nav_rail
    self.state.update()
```

---

## 5. File-by-File Task Breakdown

### 5.1 New Files to Create

| # | File | Owner | Feature | Description |
|---|------|-------|---------|-------------|
| 1 | `misaka/services/env_check_service.py` | Backend | F1 | Environment check and install service |
| 2 | `misaka/services/update_check_service.py` | Backend | F2 | Update detection and upgrade service |
| 3 | `misaka/i18n/__init__.py` | Backend | F3 | i18n translation manager |
| 4 | `misaka/i18n/en.json` | Backend | F3 | English translation strings |
| 5 | `misaka/i18n/zh_CN.json` | Backend | F3 | Simplified Chinese translation strings |
| 6 | `misaka/i18n/zh_TW.json` | Backend | F3 | Traditional Chinese translation strings |
| 7 | `misaka/ui/components/env_check_dialog.py` | Frontend | F1 | Environment check dialog UI |
| 8 | `misaka/ui/components/update_banner.py` | Frontend | F2 | Update notification banner UI |
| 9 | `tests/unit/test_env_check_service.py` | QA | F1 | Unit tests for env check service |
| 10 | `tests/unit/test_update_check_service.py` | QA | F2 | Unit tests for update check service |
| 11 | `tests/unit/test_i18n.py` | QA | F3 | Unit tests for i18n module |

### 5.2 Files to Modify

| # | File | Owner | Feature | Changes |
|---|------|-------|---------|---------|
| 1 | `misaka/config.py` | Backend | F3 | Add `SettingKeys.LANGUAGE` |
| 2 | `misaka/state.py` | Backend | F1, F2, F3 | Add env check, update, and locale state fields |
| 3 | `misaka/main.py` | Backend | F1, F2, F3 | Add services, startup hooks, i18n init |
| 4 | `misaka/services/__init__.py` | Backend | F1, F2 | Export new services |
| 5 | `misaka/ui/app_shell.py` | Frontend | F1, F3 | Add env check overlay, locale rebuild |
| 6 | `misaka/ui/components/nav_rail.py` | Frontend | F3 | Replace hardcoded labels with `t()` |
| 7 | `misaka/ui/components/chat_view.py` | Frontend | F2, F3 | Add update banner, replace strings with `t()` |
| 8 | `misaka/ui/components/chat_list.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 9 | `misaka/ui/components/message_input.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 10 | `misaka/ui/components/right_panel.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 11 | `misaka/ui/components/task_list.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 12 | `misaka/ui/components/permission_dialog.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 13 | `misaka/ui/components/connection_status.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 14 | `misaka/ui/pages/settings_page.py` | Frontend | F3 | Add language section, replace all strings |
| 15 | `misaka/ui/pages/plugins_page.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 16 | `misaka/ui/pages/extensions_page.py` | Frontend | F3 | Replace hardcoded strings with `t()` |
| 17 | `misaka/ui/pages/chat_page.py` | Frontend | F1 | Wire env check dialog |

### 5.3 Backend Engineer Task List (Ordered)

**Phase 1: i18n Infrastructure (Do First -- All other features depend on it for new strings)**

| Step | Task | File | Details |
|------|------|------|---------|
| B1 | Create i18n module | `misaka/i18n/__init__.py` | Implement `init()`, `set_locale()`, `get_locale()`, `t()`, `_flatten_dict()` |
| B2 | Create English translations | `misaka/i18n/en.json` | Full string catalog (see section 4.4) |
| B3 | Create zh-CN translations | `misaka/i18n/zh_CN.json` | Full string catalog (see section 4.4) |
| B4 | Create zh-TW translations | `misaka/i18n/zh_TW.json` | Full string catalog |
| B5 | Add LANGUAGE to SettingKeys | `misaka/config.py` | Add `LANGUAGE = "language"` to `SettingKeys` |
| B6 | Add locale to AppState | `misaka/state.py` | Add `self.locale: str = "zh-CN"` |

**Phase 2: Environment Check Service**

| Step | Task | File | Details |
|------|------|------|---------|
| B7 | Create env check service | `misaka/services/env_check_service.py` | Full implementation with `ToolStatus`, `EnvironmentCheckResult`, `EnvCheckService` |
| B8 | Add env state to AppState | `misaka/state.py` | Add `env_check_result`, `env_check_loading`, `show_env_check_dialog` |
| B9 | Register in ServiceContainer | `misaka/main.py` | Add `self.env_check_service = EnvCheckService()` |
| B10 | Add startup hook | `misaka/main.py` | Add `_run_env_check` coroutine, `page.run_task()` call |
| B11 | Export from services | `misaka/services/__init__.py` | Add `EnvCheckService` to imports and `__all__` |

**Phase 3: Update Check Service**

| Step | Task | File | Details |
|------|------|------|---------|
| B12 | Create update check service | `misaka/services/update_check_service.py` | Full implementation with `UpdateCheckResult`, `UpdateCheckService` |
| B13 | Add update state to AppState | `misaka/state.py` | Add `update_check_result`, `update_dismissed`, `update_in_progress` |
| B14 | Register in ServiceContainer | `misaka/main.py` | Add `self.update_check_service = UpdateCheckService()` |
| B15 | Add startup hook | `misaka/main.py` | Add `_run_update_check` coroutine, `page.run_task()` call |
| B16 | Export from services | `misaka/services/__init__.py` | Add `UpdateCheckService` to imports and `__all__` |

**Phase 4: i18n init in main.py**

| Step | Task | File | Details |
|------|------|------|---------|
| B17 | Add i18n init to main | `misaka/main.py` | Load saved language, call `i18n.init(locale)`, set `state.locale` |

### 5.4 Frontend Engineer Task List (Ordered)

**Phase 1: i18n String Replacement (Do in parallel with Backend Phase 1)**

| Step | Task | File | Details |
|------|------|------|---------|
| F1 | Update nav_rail | `misaka/ui/components/nav_rail.py` | Replace "Chat", "Settings", "Plugins", "Extensions" labels with `t("nav.chat")`, etc. Also update theme tooltip. |
| F2 | Update chat_view | `misaka/ui/components/chat_view.py` | Replace "Welcome to Misaka", "Select a chat...", button tooltips with `t()` calls |
| F3 | Update chat_list | `misaka/ui/components/chat_list.py` | Replace "New Chat", context menu labels with `t()` |
| F4 | Update message_input | `misaka/ui/components/message_input.py` | Replace placeholder and button labels with `t()` |
| F5 | Update right_panel | `misaka/ui/components/right_panel.py` | Replace tab labels "Files", "Tasks" with `t()` |
| F6 | Update task_list | `misaka/ui/components/task_list.py` | Replace status labels with `t()` |
| F7 | Update permission_dialog | `misaka/ui/components/permission_dialog.py` | Replace "Allow", "Deny", description text with `t()` |
| F8 | Update connection_status | `misaka/ui/components/connection_status.py` | Replace "Connected", "Disconnected" with `t()` |
| F9 | Update settings_page | `misaka/ui/pages/settings_page.py` | Replace ALL hardcoded strings (~30) with `t()` calls. Add language selector section. |
| F10 | Update plugins_page | `misaka/ui/pages/plugins_page.py` | Replace all hardcoded strings (~15) with `t()` |
| F11 | Update extensions_page | `misaka/ui/pages/extensions_page.py` | Replace all hardcoded strings (~12) with `t()` |

**Phase 2: Environment Check Dialog**

| Step | Task | File | Details |
|------|------|------|---------|
| F12 | Create env check dialog | `misaka/ui/components/env_check_dialog.py` | Full UI component with tool cards, install buttons, progress, all strings via `t()` |
| F13 | Wire into app_shell | `misaka/ui/app_shell.py` | Add env check dialog as overlay. Show/hide based on `state.show_env_check_dialog`. Wire install/dismiss callbacks. |
| F14 | Wire into chat_page | `misaka/ui/pages/chat_page.py` | Minimal: just ensure env check dialog doesn't interfere with chat stack |

**Phase 3: Update Banner**

| Step | Task | File | Details |
|------|------|------|---------|
| F15 | Create update banner | `misaka/ui/components/update_banner.py` | Banner component with update/dismiss buttons, all strings via `t()` |
| F16 | Wire into chat_view | `misaka/ui/components/chat_view.py` | Add UpdateBanner between header and error_banner. Show when `state.update_check_result.update_available` and not dismissed. |

**Phase 4: Language Switching in AppShell**

| Step | Task | File | Details |
|------|------|------|---------|
| F17 | Add locale rebuild | `misaka/ui/app_shell.py` | Add `rebuild_for_locale_change()` method. Wire settings_page language change to trigger this. |
| F18 | Wire language change | `misaka/ui/pages/settings_page.py` | Language selector `on_change` calls i18n.set_locale + state update + app_shell rebuild |

---

## 6. Flet 0.80.x Compatibility Notes

These are critical API differences that must be followed in ALL new code:

### 6.1 Button API

```python
# WRONG (old API):
ft.ElevatedButton(text="Click me")
ft.TextButton(text="Cancel")

# CORRECT (Flet 0.80.x):
ft.ElevatedButton(content="Click me")
ft.TextButton("Cancel")  # positional arg is also content
```

### 6.2 Alignment

```python
# WRONG (old API):
alignment=ft.alignment.center

# CORRECT (Flet 0.80.x):
alignment=ft.alignment.Alignment.CENTER
```

### 6.3 Dropdown

```python
# WRONG (old API):
ft.Dropdown(on_change=handler)

# CORRECT (Flet 0.80.x):
ft.Dropdown(on_select=handler)
```

### 6.4 FilePicker

```python
# WRONG (old API):
picker = ft.FilePicker()
page.overlay.append(picker)

# CORRECT (Flet 0.80.x):
picker = ft.FilePicker()
page.services.add(picker)  # FilePicker is now a Service
```

### 6.5 ColorScheme

```python
# WRONG (old API):
ft.ColorScheme(
    background="#1a1a2e",        # Removed
    on_background="#e0e0e0",     # Removed
    surface_variant="#1f2b47",   # Removed
)

# CORRECT (Flet 0.80.x):
ft.ColorScheme(
    surface="#1a1a2e",
    on_surface="#e0e0e0",
    surface_container_high="#1f2b47",
)
```

### 6.6 Existing Code Patterns to Follow

The existing codebase already uses the correct 0.80.x API. Reference these files for patterns:
- `misaka/ui/pages/settings_page.py:101` -- `ft.ElevatedButton(content="Add Provider", ...)`
- `misaka/ui/pages/plugins_page.py:52` -- `ft.ElevatedButton(content="Add Server", ...)`
- `misaka/ui/pages/settings_page.py:488` -- `ft.Dropdown(on_select=self._save_default_model)`
- `misaka/ui/pages/extensions_page.py:68` -- `alignment=ft.alignment.Alignment.CENTER`
- `misaka/ui/theme.py:46` -- `ft.ColorScheme(surface_container=..., surface_container_high=...)`

---

## 7. Testing Plan

### 7.1 Unit Tests

| Test File | Coverage Target |
|-----------|----------------|
| `tests/unit/test_env_check_service.py` | `EnvCheckService.check_tool()`, `_get_install_info()`, version parsing |
| `tests/unit/test_update_check_service.py` | `_compare_versions()`, `_get_latest_npm_version()` mock, `check_for_update()` |
| `tests/unit/test_i18n.py` | `init()`, `t()` with placeholders, `set_locale()`, `_flatten_dict()`, missing key fallback |

### 7.2 Test Patterns

```python
# test_env_check_service.py
import pytest
from unittest.mock import AsyncMock, patch
from misaka.services.env_check_service import EnvCheckService, ToolStatus

class TestEnvCheckService:
    @pytest.fixture
    def service(self):
        return EnvCheckService()

    async def test_check_tool_found(self, service):
        """Test that check_tool returns installed=True when binary exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"v20.11.1\n", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await service.check_tool("node", "--version")
            assert result.is_installed is True
            assert result.version == "20.11.1"

    async def test_check_tool_not_found(self, service):
        """Test that check_tool returns installed=False when binary missing."""
        with patch("shutil.which", return_value=None):
            result = await service.check_tool("nonexistent")
            assert result.is_installed is False
            assert result.version is None

    async def test_check_all_returns_aggregate(self, service):
        """Test check_all returns results for all 4 tools."""
        with patch.object(service, "check_tool") as mock_check:
            mock_check.return_value = ToolStatus(
                name="test", command="test",
                version="1.0", is_installed=True,
                install_url="", install_command="",
            )
            result = await service.check_all()
            assert len(result.tools) == 4
            assert result.all_installed is True
```

```python
# test_update_check_service.py
from misaka.services.update_check_service import UpdateCheckService

class TestUpdateCheckService:
    def test_compare_versions_newer(self):
        assert UpdateCheckService._compare_versions("1.0.25", "1.1.0") is True

    def test_compare_versions_same(self):
        assert UpdateCheckService._compare_versions("1.0.25", "1.0.25") is False

    def test_compare_versions_older(self):
        assert UpdateCheckService._compare_versions("1.1.0", "1.0.25") is False

    def test_compare_versions_major(self):
        assert UpdateCheckService._compare_versions("1.9.9", "2.0.0") is True
```

```python
# test_i18n.py
import misaka.i18n as i18n

class TestI18n:
    def setup_method(self):
        i18n.init("en")

    def test_basic_translation(self):
        assert i18n.t("nav.chat") == "Chat"

    def test_fallback_to_key(self):
        assert i18n.t("nonexistent.key") == "nonexistent.key"

    def test_placeholder_substitution(self):
        result = i18n.t("update.available", version="1.1.0", current="1.0.25")
        assert "1.1.0" in result
        assert "1.0.25" in result

    def test_locale_switch(self):
        i18n.set_locale("zh-CN")
        assert i18n.t("nav.chat") == "聊天"
        i18n.set_locale("en")
        assert i18n.t("nav.chat") == "Chat"

    def test_flatten_dict(self):
        result = i18n._flatten_dict({"a": {"b": {"c": "value"}}})
        assert result == {"a.b.c": "value"}
```

### 7.3 Integration Test Considerations

- Environment check tests should mock subprocess calls (do not actually install software)
- Update check tests should mock npm registry responses
- i18n tests should verify that all keys used in UI files exist in all 3 locale JSON files
- Consider adding a lint script: `python scripts/check_i18n_keys.py` that scans all `.py` files for `t("...")` calls and verifies they exist in all JSON files

---

## Appendix A: Import Graph for New Code

```
misaka/main.py
  ├── misaka/services/env_check_service.py
  │     └── misaka/config.py (IS_WINDOWS, IS_MACOS, IS_LINUX, get_expanded_path)
  │     └── misaka/utils/platform.py (find_claude_binary, clear_claude_cache)
  ├── misaka/services/update_check_service.py
  │     └── misaka/utils/platform.py (find_claude_binary, get_claude_version, clear_claude_cache)
  │     └── misaka/config.py (IS_WINDOWS, get_expanded_path)
  ├── misaka/i18n/__init__.py (standalone, no dependencies)
  └── misaka/state.py (updated with new fields)

misaka/ui/app_shell.py
  └── misaka/ui/components/env_check_dialog.py
        └── misaka/i18n (t)

misaka/ui/components/chat_view.py
  └── misaka/ui/components/update_banner.py
        └── misaka/i18n (t)

All UI files:
  └── misaka/i18n (t)
```

## Appendix B: Migration Checklist

No database migrations are needed for these features. All state is either:
- In-memory (env check results, update check results)
- Stored via the existing `settings` key-value table (language preference)

The `settings` table already exists and supports arbitrary key-value pairs via `get_setting(key)` / `set_setting(key, value)`.

## Appendix C: Risk Assessment

| Risk | Mitigation |
|------|-----------|
| `npm install -g` fails on Windows due to permissions | Show download URL as fallback; detect permission errors and suggest running as admin |
| npm registry unreachable (firewall, proxy) | Use `npm view` first (respects proxy config); timeout after 5s; cache last-known version |
| i18n key drift (keys in code don't match JSON) | Lint script to verify all `t()` calls have matching keys in all locale files |
| Flet version incompatibility | Pin Flet to `>=0.27.0,<1.0`; test with latest 0.80.x before release |
| Subprocess hangs on Windows | Use `asyncio.wait_for()` with timeout on all subprocess calls |
| Install command blocks UI thread | All install operations are async; UI shows progress spinner |
