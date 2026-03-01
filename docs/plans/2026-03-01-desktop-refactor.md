# Desktop Refactor & New Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor chat module (model selection via /model command, conversation type dropdown, command icon button), redesign settings page (remove claude code card, replace CLI settings with Claude Code Router multi-config system), unify fonts, add Thinking animation, and enable Flet debug mode.

**Architecture:** Changes span across UI components (chat_view, message_input, settings_page, message_item), services (cli_settings_service), commands, state, theme, database models/migrations, and i18n. The refactoring follows the existing pattern: UI → AppState → ServiceContainer → Database.

**Tech Stack:** Python 3.10+, Flet 0.80.x, SQLite, claude-agent-sdk

---

## Requirement Summary

From `docs/demand/桌面端修改内容20260301.txt`:

1. **Chat Module Refactoring:**
   - 1a. Conversation type (mode) selection changed to dropdown format (currently pill buttons)
   - 1b. Remove model selection dropdown from chat header; add `/model` slash command that shows a sub-menu of model choices (Default, Sonnet, Opus, Haiku) read from `~/.claude/settings.json` env vars (ANTHROPIC_MODEL, ANTHROPIC_DEFAULT_OPUS_MODEL, ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_DEFAULT_SONNET_MODEL)
   - 1c. Add a "command" icon button next to the attach file button in the input area; clicking it shows the same slash command menu as typing `/`
   - 1d. Audit chat module: verify claude-agent-sdk integration correctly shows skill/agent/mcp events in real-time; fix empty "Claude" or "You" messages being rendered
   - 1e. Add wave/shimmer text color animation for status text like "Thinking"

2. **Settings Module Refactoring:**
   - 2a. Remove the "Claude Code" card (the one with default working dir + default model dropdown)
   - 2b. Rename "Claude CLI Settings" card to "Claude Code Router"; rewrite as a multi-config list supporting CRUD
   - 2c. Each config has: provider name, API Key, request URL, main model, Haiku model, Opus model, Sonnet model, Agent Team toggle, config JSON editor
   - 2d. Model fields and Agent Team toggle are bidirectionally bound with the config JSON (`env` section)
   - 2e. "Enable" button writes the config JSON to `~/.claude/settings.json`; shows "In Use" state
   - 2f. Default config auto-initialized from current `~/.claude/settings.json` on first launch

3. **Font Unification:**
   - 3a. Chinese text: Microsoft YaHei (微软雅黑); English/code: Consolas

4. **Flet Debug Mode:**
   - 4a. Enable debug mode, hot reload, and verbose logging in dev environment

---

## Task 1: Database — Add `router_configs` Table

**Files:**
- Modify: `misaka/db/models.py`
- Modify: `misaka/db/database.py`
- Modify: `misaka/db/sqlite_backend.py`
- Modify: `misaka/db/migrations.py`

**Description:**
Add a new `RouterConfig` dataclass model and database CRUD for storing multiple Claude Code Router configurations.

**Model:**
```python
@dataclass
class RouterConfig:
    id: str
    name: str                  # provider/config name
    api_key: str = ""
    base_url: str = ""
    main_model: str = ""       # maps to ANTHROPIC_MODEL
    haiku_model: str = ""      # maps to ANTHROPIC_DEFAULT_HAIKU_MODEL
    opus_model: str = ""       # maps to ANTHROPIC_DEFAULT_OPUS_MODEL
    sonnet_model: str = ""     # maps to ANTHROPIC_DEFAULT_SONNET_MODEL
    agent_team: bool = False   # maps to CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="1"
    config_json: str = "{}"    # full settings.json content
    is_active: int = 0         # 0 or 1
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""
```

**Database abstract methods to add:**
- `get_all_router_configs() -> list[RouterConfig]`
- `get_router_config(config_id: str) -> RouterConfig | None`
- `get_active_router_config() -> RouterConfig | None`
- `create_router_config(name: str, **kwargs) -> RouterConfig`
- `update_router_config(config_id: str, **kwargs) -> RouterConfig | None`
- `delete_router_config(config_id: str) -> bool`
- `activate_router_config(config_id: str) -> bool`

**Migration:** Add `router_configs` table in migration v2.

---

## Task 2: Service — RouterConfigService

**Files:**
- Create: `misaka/services/router_config_service.py`
- Modify: `misaka/main.py` (register in ServiceContainer)

**Description:**
Create a service that manages router configurations and handles the bidirectional binding logic between form fields and config JSON. Also handles the "activate" logic (write config JSON to `~/.claude/settings.json`) and the default config initialization.

**Key methods:**
- `get_all() -> list[RouterConfig]`
- `get_active() -> RouterConfig | None`
- `create(name, **fields) -> RouterConfig`
- `update(config_id, **fields) -> RouterConfig | None`
- `delete(config_id) -> bool`
- `activate(config_id) -> bool` — writes config_json to `~/.claude/settings.json`
- `sync_form_to_json(config: RouterConfig, field_name: str, value: str | bool) -> str` — update config_json when form field changes
- `sync_json_to_form(config_json: str) -> dict` — extract form field values from config JSON
- `ensure_default_config()` — on first launch, create a Default config from current `~/.claude/settings.json`

**Bidirectional binding mapping:**
- `main_model` ↔ `env.ANTHROPIC_MODEL`
- `haiku_model` ↔ `env.ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `opus_model` ↔ `env.ANTHROPIC_DEFAULT_OPUS_MODEL`
- `sonnet_model` ↔ `env.ANTHROPIC_DEFAULT_SONNET_MODEL`
- `agent_team=True` ↔ `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="1"` (False = remove key)
- When model field is empty, remove the corresponding key from JSON (don't set to "")

---

## Task 3: Commands — Add `/model` Command

**Files:**
- Modify: `misaka/commands.py`
- Modify: `misaka/ui/components/message_input.py`
- Modify: `misaka/ui/pages/chat_page.py`
- Modify: `misaka/ui/components/chat_view.py`
- Modify: `misaka/state.py`

**Description:**
Add a `/model` slash command that, when selected, shows a sub-menu of available models instead of the normal command behavior. The model list is read from `~/.claude/settings.json` env vars. Default is selected by default.

**Command definition:**
```python
SlashCommand(
    name="model",
    description="切换模型",
    icon=ft.Icons.MODEL_TRAINING,
    immediate=True,  # handled in UI, not sent as prompt
)
```

**Model sub-menu behavior in MessageInput:**
- When user selects `/model`, instead of setting a badge or executing, show a second-level menu with model options
- Model options: Default, Sonnet, Opus, Haiku
- Display names are read from `~/.claude/settings.json` env section via `CliSettingsService`:
  - `ANTHROPIC_MODEL` → shown as value or "Default"
  - `ANTHROPIC_DEFAULT_SONNET_MODEL` → shown as value or "Sonnet"
  - `ANTHROPIC_DEFAULT_OPUS_MODEL` → shown as value or "Opus"
  - `ANTHROPIC_DEFAULT_HAIKU_MODEL` → shown as value or "Haiku"
- Selecting a model calls `on_model_change` callback and hides the menu
- The selected model value is passed to claude-agent-sdk via `send_message(model=...)`
- Add `selected_model` to AppState to track current model selection (default: "default")

**Also in ChatView:**
- Remove `self._model_dropdown` from the header entirely
- Remove the model dropdown from the header row
- Keep the mode buttons as-is for now (they get converted to dropdown in Task 5)

---

## Task 4: Chat Input — Add Command Icon Button

**Files:**
- Modify: `misaka/ui/components/message_input.py`

**Description:**
Add a command icon button (e.g., slash/terminal icon) next to the attach file button. Clicking it triggers the same command popup menu as typing `/`.

**Implementation:**
- Add a new `IconButton` with `ft.Icons.TERMINAL` or `ft.Icons.CODE` icon
- Place it to the right of the attach button
- On click, call `self._show_command_menu(filter_commands(""))` to show all commands
- Update input_row to include the new button

---

## Task 5: Chat View — Mode Selector as Dropdown

**Files:**
- Modify: `misaka/ui/components/chat_view.py`

**Description:**
Replace the pill-shaped mode toggle buttons with a dropdown selector for conversation type (Code/Plan/Ask).

**Implementation:**
- Replace the `_mode_buttons` list with a `ft.Dropdown` similar to how the model dropdown was built
- Options: Code, Plan, Ask
- On change, call `self._handle_mode_change(mode)`
- Place it in the header where the mode buttons were

---

## Task 6: Chat Module — Fix Empty Messages & Audit SDK Integration

**Files:**
- Modify: `misaka/ui/components/message_item.py`
- Modify: `misaka/ui/components/message_list.py`
- Modify: `misaka/ui/pages/chat_page.py`

**Description:**
- In `MessageItem._build_ui()`, skip rendering if all content blocks are empty (no text, no tool calls)
- In `MessageList`, filter out empty messages before rendering
- Audit `ChatPage.send_to_claude()` to ensure skill/agent/mcp tool_use and tool_result events are properly captured and displayed via streaming blocks
- Verify `_dispatch_message` in ClaudeService handles all message types that the SDK emits

**Empty message fix:**
```python
# In MessageItem._build_ui() or MessageList, skip messages where:
# - All text blocks have empty/whitespace-only text
# - No tool_use or tool_result blocks exist
# - No code blocks exist
```

---

## Task 7: Chat Module — Thinking Animation

**Files:**
- Modify: `misaka/ui/components/message_list.py` (or wherever the streaming "Thinking" text is displayed)
- Possibly modify: `misaka/ui/components/connection_status.py`

**Description:**
Add a wave/shimmer text color animation for status text like "Thinking" that appears during streaming. This should be a CSS-like gradient animation on the text color.

**Implementation approach:**
- Use Flet's `ft.ShaderMask` or animated gradient on the "Thinking" text
- Or use `ft.AnimatedSwitcher` with a `ft.Text` that cycles through color opacity
- A simpler approach: use `ft.ProgressRing` + animated opacity on the text via Flet's animation system (`ft.Animation`, `animate_opacity`)
- The most visually appealing: use a shimmer effect with `ft.ShaderMask` and a `ft.LinearGradient` that animates its offset

---

## Task 8: Settings — Remove Claude Code Card

**Files:**
- Modify: `misaka/ui/pages/settings_page.py`

**Description:**
Remove the `_build_cli_section()` method and its corresponding card from the settings page controls list. This removes the "Claude Code" card with default working directory and default model.

**Steps:**
- Remove `cli_section = self._build_cli_section()` call
- Remove `self._wrap_card(cli_section)` from `self.controls`
- Remove `_build_cli_section`, `_save_working_dir`, `_save_default_model` methods
- Keep the settings keys in the DB for backward compatibility (don't delete data)

---

## Task 9: Settings — Claude Code Router (Multi-Config System)

**Files:**
- Modify: `misaka/ui/pages/settings_page.py`
- Modify: `misaka/i18n/zh_CN.json`
- Modify: `misaka/i18n/en.json`
- Modify: `misaka/i18n/zh_TW.json`

**Description:**
Replace the existing "Claude CLI Settings" card with a new "Claude Code Router" card that provides a multi-config list with CRUD operations.

**UI Structure:**
```
Claude Code Router
├── Config list (scrollable)
│   ├── Config item 1 [Default] [Active/In Use badge] [Edit] [Delete]
│   ├── Config item 2 [Enable] [Edit] [Delete]
│   └── ...
├── [+ Add Configuration] button
```

**Config form dialog (for Add/Edit):**
```
┌─ Add/Edit Configuration ─────────────────────┐
│ Provider Name:     [________________]         │
│ API Key:           [________________] 👁       │
│ Request URL:       [________________]         │
│ Main Model:        [________________]         │
│ Haiku Model:       [________________]         │
│ Opus Model:        [________________]         │
│ Sonnet Model:      [________________]         │
│ Agent Team Mode:   [  Toggle  ]               │
│ ─────────────────────────────────────         │
│ Config JSON:                                  │
│ ┌─────────────────────────────────┐           │
│ │ { ... }                         │           │
│ └─────────────────────────────────┘           │
│                        [Cancel] [Save]        │
└───────────────────────────────────────────────┘
```

**Bidirectional binding in the form:**
- When user changes a model text field → update corresponding key in config JSON env section
- When user changes agent_team toggle → add/remove CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS in config JSON env
- When user edits config JSON directly → update form fields to match
- If a model field is cleared, remove the key from JSON (don't set to "")
- If JSON doesn't have env section, create one when form fields are filled

**Enable/Activate behavior:**
- Click "Enable" → calls `RouterConfigService.activate(config_id)` which writes config_json to `~/.claude/settings.json`
- The enabled config shows "In Use" badge and the enable button becomes disabled
- Only one config can be active at a time

**Default initialization:**
- On app startup, call `RouterConfigService.ensure_default_config()`
- This checks if any configs exist; if not, reads current `~/.claude/settings.json` and creates a "Default" config with `is_active=1`
- The "Default" config's `config_json` = current settings.json content but with `env: {}`... wait, re-reading the requirement: the default JSON data is the full `~/.claude/settings.json` content, but the `env` section is `{}` (empty). No — re-reading again: "配置 JSON 新增会有默认 JSON 数据，即为读取 ~/.claude/settings.json 中的内容，但其中 env 配置为 {}（空配置 json）" — this is for NEW configs (Add button), not the Default config. The Default config reads the full settings.json as-is and is active. Let me clarify:
  - **New config** (Add button): config_json defaults to settings.json content with `env: {}`
  - **Default config** (first launch init): config_json = full settings.json content as-is, is_active = 1

---

## Task 10: Font Unification

**Files:**
- Modify: `misaka/ui/theme.py`
- Modify: `misaka/main.py`

**Description:**
Set the global font family so that Chinese text uses Microsoft YaHei (微软雅黑) and English/code text uses Consolas.

**Implementation:**
- In `theme.py`, update `FONT_FAMILY` to `"Microsoft YaHei, Consolas, Segoe UI, sans-serif"`
- In `MONO_FONT_FAMILY`, ensure Consolas is the primary: `"Consolas, Cascadia Code, JetBrains Mono, monospace"`
- In `get_dark_theme()` and `get_light_theme()`, set `font_family` on the Theme object
- In `main.py`, set `page.fonts` if needed for custom font registration (Flet 0.80.x supports system fonts directly)

---

## Task 11: Flet Debug Mode

**Files:**
- Modify: `misaka/main.py`

**Description:**
When running in development environment, enable Flet's debug mode, hot reload, and verbose logging.

**Implementation:**
- Check for `MISAKA_DEBUG` env var or detect if running via `pip install -e`
- Set logging level to DEBUG when debug mode is on
- Pass `ft.run(_main, ..., debug=True)` or appropriate Flet 0.80.x flags for hot reload
- Flet 0.80.x: `ft.run(target, ..., web_renderer=..., view=...)` — check Flet docs for debug options
- Alternative: use `flet run --hot` command documented in CLAUDE.md

---

## Task 12: i18n Updates

**Files:**
- Modify: `misaka/i18n/zh_CN.json`
- Modify: `misaka/i18n/en.json`
- Modify: `misaka/i18n/zh_TW.json`

**Description:**
Add all new i18n keys needed for the refactored features:

```json
{
  "settings.router_title": "Claude Code Router",
  "settings.router_desc": "管理多个 Claude Code 配置，快速切换不同环境",
  "settings.router_add": "添加配置",
  "settings.router_edit": "编辑配置",
  "settings.router_name": "供应商名称",
  "settings.router_api_key": "API Key",
  "settings.router_base_url": "请求地址",
  "settings.router_main_model": "主模型",
  "settings.router_haiku_model": "Haiku 模型",
  "settings.router_opus_model": "Opus 模型",
  "settings.router_sonnet_model": "Sonnet 模型",
  "settings.router_agent_team": "Agent Team 模式",
  "settings.router_config_json": "配置 JSON",
  "settings.router_enable": "启用",
  "settings.router_in_use": "使用中",
  "settings.router_default": "Default",
  "settings.router_activate_confirm": "确认启用此配置？这将覆盖 ~/.claude/settings.json",
  "chat.command_menu": "命令菜单",
  "chat.select_model": "选择模型"
}
```

---

## Task Execution Order

```
Task 1 (DB model + migration)
    ↓
Task 2 (RouterConfigService)
    ↓
┌───────────────────┬──────────────────────────┐
│ Task 3 (/model)   │ Task 9 (Router settings) │
│ Task 4 (cmd icon) │ Task 8 (remove card)     │
│ Task 5 (mode dd)  │ Task 10 (fonts)          │
│ Task 6 (fix msgs) │ Task 11 (debug mode)     │
│ Task 7 (thinking) │ Task 12 (i18n)           │
└───────────────────┴──────────────────────────┘
    ↓
Code Review & QA Testing
```

Tasks 1-2 must be sequential (dependencies).
Tasks 3-12 can be parallelized between frontend and backend engineers.
Frontend: Tasks 3, 4, 5, 6, 7, 9, 12
Backend: Tasks 1, 2, 8, 10, 11
