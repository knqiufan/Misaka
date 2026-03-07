# Misaka 技术架构文档

> 基于本地代码结构分析生成 | 版本 0.1.0

## 1. 项目概述

### 1.1 定位

Misaka 是 Claude Code 的桌面 GUI 客户端，基于 Python 3.10+ 与 [Flet](https://flet.dev) 0.27.x（Flutter 风格 UI）构建，封装 `claude-agent-sdk`，提供多轮流式对话、会话管理、文件浏览、MCP 服务集成和技能管理，采用 Material Design 3 界面。

### 1.2 外部依赖

- **Node.js** + 全局安装的 `@anthropic-ai/claude-code` CLI
- **Python 3.10+**

### 1.3 核心依赖（pyproject.toml）

| 依赖 | 版本 | 用途 |
|------|------|------|
| flet | >=0.27.0,<1.0 | UI 框架 |
| claude-agent-sdk | >=0.1.5 | Claude 对话与工具调用 |
| watchdog | >=4.0.0 | 文件监控 |
| aiofiles | >=24.0.0 | 异步文件 I/O |
| Pygments | >=2.18.0 | 代码高亮 |
| anyio | >=4.0.0 | 异步运行时 |

---

## 2. 架构分层

```
┌─────────────────────────────────────────────────────────────────────┐
│                    UI Layer (Flet Controls)                          │
│  AppShell → ChatPage / SettingsPage / PluginsPage / ExtensionsPage   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AppState (集中式状态)                              │
│  state.update() 触发 Flet 重渲染                                      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ServiceContainer (依赖注入)                         │
│  所有服务单例，共享 DatabaseBackend                                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│   DatabaseBackend (SQLite)     │   │   Claude SDK / Claude CLI       │
└───────────────────────────────┘   └───────────────────────────────┘
```

---

## 3. 目录结构

```
Misaka/
├── misaka/                          # 主程序包
│   ├── main.py                      # 入口点：创建 DB、ServiceContainer、AppState、AppShell
│   ├── config.py                    # 路径、环境变量、SettingKeys
│   ├── state.py                     # AppState 集中状态
│   ├── commands.py                  # 斜杠命令定义（immediate=True 在 UI 处理，False 注入 Claude）
│   │
│   ├── db/                          # 数据库层
│   │   ├── database.py              # DatabaseBackend ABC + create_database()
│   │   ├── sqlite_backend.py        # SQLite 实现（WAL 模式）
│   │   ├── models.py                # 数据模型（dataclass）
│   │   ├── migrations.py            # 增量迁移（_schema_version）
│   │   └── row_mappers.py           # DB 行 → 模型映射
│   │
│   ├── services/                    # 服务层（业务逻辑）
│   │   ├── chat/                    # Claude 对话
│   │   │   ├── claude_service.py    # Claude SDK 封装、流式、环境
│   │   │   ├── session_service.py   # 会话 CRUD
│   │   │   ├── message_service.py   # 消息持久化
│   │   │   └── permission_service.py  # 工具权限请求
│   │   ├── settings/                # 设置
│   │   │   ├── settings_service.py  # 键值设置
│   │   │   ├── cli_settings_service.py
│   │   │   └── router_config_service.py
│   │   ├── mcp/                     # MCP 服务
│   │   │   └── mcp_service.py
│   │   ├── skills/                  # 技能
│   │   │   ├── skill_service.py
│   │   │   └── env_check_service.py
│   │   ├── file/                    # 文件
│   │   │   ├── file_service.py
│   │   │   └── update_check_service.py
│   │   ├── task/                    # 任务
│   │   │   └── task_service.py
│   │   ├── session/                 # 会话导入
│   │   │   └── session_import_service.py
│   │   └── common/                  # 公共
│   │       └── claude_env_builder.py
│   │
│   ├── ui/                          # UI 层
│   │   ├── common/                  # 公共 UI
│   │   │   ├── theme.py             # MD3 主题、Misaka 设计系统
│   │   │   ├── app_shell.py         # 根布局（NavRail + 内容区）
│   │   │   └── context_menu.py
│   │   ├── chat/                    # 聊天
│   │   │   ├── components/          # ChatView、ChatList、MessageList、MessageInput 等
│   │   │   └── pages/               # ChatPage、StreamHandler
│   │   ├── settings/                # 设置页
│   │   ├── skills/                  # 技能/扩展页
│   │   ├── file/                    # 文件树、预览、文件夹选择
│   │   ├── task/                    # 任务列表
│   │   ├── navigation/              # NavRail
│   │   ├── panels/                  # RightPanel、ResizeHandle、OffsetMenu
│   │   ├── dialogs/                 # 权限、导入、环境检查
│   │   ├── status/                  # 连接状态、更新横幅
│   │   └── pages/                   # PluginsPage
│   │
│   ├── utils/                       # 工具
│   │   ├── platform.py              # 平台检测、Claude 二进制、Git Bash
│   │   ├── file_utils.py
│   │   ├── path_safety.py
│   │   └── time_utils.py
│   │
│   └── i18n/                        # 国际化
│       ├── __init__.py              # t()、init()、set_locale()
│       ├── en.json
│       ├── zh_CN.json
│       └── zh_TW.json
│
├── tests/                           # 测试
│   ├── conftest.py                  # 内存 SQLiteBackend 等 fixture
│   ├── unit/
│   └── integration/
│
├── docs/                            # 文档
├── assets/                          # 图标等资源
└── pyproject.toml
```

---

## 4. 核心模块详解

### 4.1 入口与生命周期（main.py）

```python
# 启动流程
main() → _setup_logging() → ft.run(_main, assets_dir=assets)

# _main(page) 流程
1. ensure_data_dir()
2. db = create_database() → db.initialize()
3. services = ServiceContainer(db)
4. services.router_config_service.ensure_default_config()
5. state = AppState(page)
6. 应用主题、加载会话、MCP 服务器
7. state.services = services
8. i18n.init(locale)
9. app_shell = AppShell(state)
10. page.add(app_shell)
11. 运行 env_check、update_check
12. page.on_disconnect = on_disconnect → services.close()
```

**ServiceContainer 依赖关系：**

- `db` → 所有需要持久化的服务
- `permission_service` → 无依赖
- `settings_service` → db
- `session_service` / `message_service` → db
- `claude_service` → db, permission_service
- `router_config_service` → db, cli_settings_service

### 4.2 状态管理（state.py）

**AppState 主要属性：**

| 分类 | 属性 | 说明 |
|------|------|------|
| 服务 | services, mcp_servers_sdk | 服务容器与 MCP 配置 |
| 会话 | _sessions, _session_map, current_session_id | 会话列表与当前会话 |
| 消息 | messages, has_more_messages | 当前会话消息 |
| 流式 | is_streaming, streaming_blocks, streaming_session_id | 流式输出 |
| 后台流 | background_streams | detached 会话 |
| 权限 | pending_permission, _permission_future | 权限弹窗 |
| 任务 | tasks | 任务列表 |
| 面板 | left_panel_open, right_panel_open, right_panel_tab | 面板开关 |
| 主题 | theme_mode, accent_color | 主题模式与强调色 |
| 其他 | file_tree_root, sdk_session_id, last_token_usage, error_message | |

**状态更新：** 服务修改 state 后调用 `state.update()` 触发 `page.update()`。

### 4.3 数据库层（db/）

**DatabaseBackend 接口：**

- 会话：get_all_sessions, get_session, create_session, update_session_*, delete_session
- 消息：get_messages（游标分页）, add_message, add_messages_batch, clear_session_messages
- 设置：get_setting, set_setting, get_all_settings
- 任务：get_tasks_by_session, create_task, update_task, delete_task
- 路由配置：get_all_router_configs, get_active_router_config, create_router_config, update_router_config, activate_router_config 等

**SQLiteBackend：**

- WAL 模式、外键约束
- `row_factory = sqlite3.Row`
- 表：chat_sessions, messages, settings, tasks, router_configs

**迁移：**

- `_schema_version` 表记录版本
- 当前 SCHEMA_VERSION = 4
- v1：会话、消息字段扩展
- v2：router_configs 表
- v3：会话 mode 从 `code` 迁移到 `agent`
- v4：删除遗留 `api_providers` 表

### 4.4 Claude 集成（claude_service.py）

**ClaudeService：**

- 封装 `ClaudeSDKClient` 做多轮对话
- 支持流式、中断、权限模式切换
- `build_claude_env()` 构建子进程环境（PATH、Git Bash、API Key）
- `_build_options()` 构建 ClaudeAgentOptions

**权限流程：**

1. SDK 调用 `can_use_tool` → PermissionService.register()
2. 创建 asyncio.Future，等待 5 分钟
3. UI 显示 PermissionDialog
4. 用户决策 → PermissionService.resolve()

**Windows 特殊处理：**

- `.cmd` 包装解析为实际 `.js` 入口
- `CLAUDE_CODE_GIT_BASH_PATH` 环境变量
- PATH 扩展常见 npm/nvm 路径

### 4.5 流式处理（stream_handler.py）

**StreamHandler：**

- 管理单次流式对话
- 回调：text_delta、tool_use、tool_result、permission
- 区分 foreground / background 流
- 自动允许：Read、Glob、Grep、WebFetch、WebSearch、LS
- 编辑类工具：Edit 等需用户确认

### 4.6 斜杠命令（commands.py）

| 命令 | immediate | 行为 |
|------|-----------|------|
| model | True | 切换模型 |
| help | True | 显示帮助 |
| clear | True | 清空对话 |
| cost | True | Token 用量 |
| compact | False | 注入压缩上下文提示 |
| doctor | False | 注入诊断提示 |
| init | False | 初始化 CLAUDE.md |
| review | False | 代码审查 |
| terminal-setup | False | 终端配置 |
| memory | False | 编辑项目记忆 |

### 4.7 主题系统（theme.py）

- 配色：Neo Minimal Tech（深色 / 浅色）
- 强调色：默认 #6366f1
- 组件工厂：make_text_field, make_dropdown, make_card, make_button, make_badge 等
- 代码高亮：CODE_THEME_GITHUB_DARK, CODE_THEME_ONE_DARK
- 系统 / 浅色 / 深色三种模式

### 4.8 国际化（i18n/）

- 支持：en, zh-CN, zh-TW
- 默认：zh-CN
- 扁平化 JSON：`{"nav": {"chat": "Chat"}}` → `{"nav.chat": "Chat"}`
- `t(key, **kwargs)` 支持占位符
- 语言变更时重建页面：`AppShell.rebuild_for_locale_change()`

---

## 5. 依赖与数据流

```
main.py
  ├── DatabaseBackend
  ├── ServiceContainer
  │   ├── PermissionService
  │   ├── SettingsService
  │   ├── SessionService
  │   ├── MessageService
  │   ├── TaskService
  │   ├── FileService
  │   ├── MCPService
  │   ├── ClaudeService
  │   ├── EnvCheckService
  │   ├── UpdateCheckService
  │   ├── SkillService
  │   ├── SessionImportService
  │   ├── CliSettingsService
  │   └── RouterConfigService
  ├── AppState
  └── AppShell
      ├── NavRail → 页面切换
      ├── ChatPage
      │   ├── ChatList
      │   ├── ChatView
      │   │   ├── MessageList
      │   │   └── MessageInput → ClaudeService
      │   ├── RightPanel
      │   │   ├── FileTree
      │   │   └── TaskList
      │   └── StreamHandler
      ├── SettingsPage
      ├── PluginsPage
      └── ExtensionsPage
```

---

## 6. 数据模型（models.py）

| 模型 | 说明 |
|------|------|
| ChatSession | 会话 id、title、model、system_prompt、working_directory、sdk_session_id、status、mode |
| Message | content 为 JSON（MessageContentBlock 列表） |
| MessageContentBlock | type: text/tool_use/tool_result/code |
| TaskItem | 任务 id、session_id、title、status、description |
| RouterConfig | Claude Code Router 配置 |
| TokenUsage | input_tokens、output_tokens、cache_*、cost_usd |

---

## 7. 配置与路径（config.py）

| 配置项 | 默认值 |
|--------|--------|
| DATA_DIR | ~/.misaka/（可通过 MISAKA_DATA_DIR 覆盖） |
| DB_PATH | DATA_DIR/misaka.db |
| LOG_PATH | DATA_DIR/misaka.log |

**SettingKeys：**

- default_model, default_system_prompt, theme, permission_mode
- max_thinking_tokens, dangerously_skip_permissions
- claude_debug_log, language, accent_color

---

## 8. 平台相关

- **Windows**：Claude CLI `.cmd` 解析、Git Bash 路径、PATH 扩展
- **macOS/Linux**：标准 PATH 扩展
- **数据库**：仅 SQLite，跨平台

---

## 9. 代码规范

- `from __future__ import annotations`
- `TYPE_CHECKING` 隔离类型导入
- 行宽 100 字符（Ruff）
- mypy 严格模式
- 异步 UI：`page.run_task(coro)`
- pytest `asyncio_mode = "auto"`
