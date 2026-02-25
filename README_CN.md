# Misaka

**[中文说明](README_CN.md)** · [English](README.md)

> 基于 Python 和 [Flet](https://flet.dev) 构建的 Claude Code 桌面 GUI 客户端。

Misaka 将 Claude Code 的强大能力带入精致的原生桌面体验——多轮流式对话、会话管理、文件树浏览、MCP 服务器集成等功能，全部融入简洁的 Material Design 3 界面。

---

## ✨ 功能特性

| 分类 | 详情 |
|---|---|
| **多模型对话** | 在任意会话中自由切换 Claude Sonnet、Opus、Haiku |
| **流式响应** | 实时逐 token 渲染，支持随时中止 |
| **会话管理** | 创建、重命名、归档、删除、搜索对话会话 |
| **三种对话模式** | `Code`（编码）· `Plan`（规划）· `Ask`（问答）——与 Claude Code 原生模式直接对应 |
| **文件树浏览器** | 在右侧面板浏览项目目录，支持文件实时预览 |
| **MCP 服务器支持** | 从 Claude 配置文件加载并管理 Model Context Protocol 服务器 |
| **技能管理** | 在「技能」页面查看和管理 Claude Code Skills |
| **导入 CLI 会话** | 将 Claude Code CLI 的历史会话导入到 Misaka |
| **多语言界面** | English · 简体中文 · 繁體中文 |
| **主题切换** | 浅色 / 深色 / 跟随系统——重启后自动恢复 |
| **API 提供商配置** | 添加并管理多个 Anthropic API 提供商，支持自定义 Base URL |
| **权限控制** | 细粒度工具权限模式，支持交互式审批对话框 |
| **更新提醒** | 启动时自动检测 Claude Code CLI 是否有新版本 |
| **跨平台** | Windows · macOS · Linux |

---

## 📋 环境要求

- **Python** 3.10 及以上
- **Node.js**（用于 Claude Code CLI）
- **Claude Code CLI** — 通过 npm 安装：
  ```bash
  npm install -g @anthropic-ai/claude-code
  ```
- **Anthropic API Key** — 通过环境变量设置，或在应用「设置」页面中配置

---

## 🚀 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/knqiufan/Misaka.git
cd Misaka

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 设置 API Key（或在「设置」页面中配置）
set ANTHROPIC_API_KEY=sk-ant-...    # Windows
export ANTHROPIC_API_KEY=sk-ant-... # macOS / Linux

# 4. 启动 Misaka
misaka
# 或
python -m misaka.main
```

应用窗口默认尺寸为 **1280 × 860**（最小 800 × 600）。所有数据——会话、设置、日志——均存储在 `~/.misaka/` 目录下。

---

## 🗂 项目结构

```
Misaka/
├── misaka/
│   ├── main.py                 # 入口 & 依赖注入容器
│   ├── config.py               # 路径、环境变量、配置键
│   ├── state.py                # 响应式应用状态
│   ├── db/                     # 数据库层（SQLite / SeekDB）
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── sqlite_backend.py
│   │   └── seekdb_backend.py
│   ├── services/               # 业务逻辑服务层
│   │   ├── claude_service.py   # Claude Agent SDK 集成
│   │   ├── session_service.py  # 会话管理
│   │   ├── message_service.py  # 消息管理
│   │   ├── provider_service.py # API 提供商管理
│   │   ├── mcp_service.py      # MCP 服务器管理
│   │   ├── settings_service.py # 设置持久化
│   │   ├── permission_service.py
│   │   ├── skill_service.py
│   │   └── ...
│   ├── ui/
│   │   ├── app_shell.py        # 根布局外壳
│   │   ├── theme.py            # Material Design 3 主题
│   │   ├── components/         # 可复用 UI 组件
│   │   └── pages/              # 聊天 · 设置 · 插件 · 技能
│   └── i18n/                   # 多语言文件（en / zh_CN / zh_TW）
├── assets/                     # 应用图标
├── tests/                      # 单元测试 & 集成测试
├── docs/                       # 架构设计文档
├── pyproject.toml
└── requirements.txt
```

---

## ⚙️ 配置说明

### API Key

在启动前设置环境变量，或在应用内「设置 → API 提供商」中添加：

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 数据目录

覆盖默认的 `~/.misaka/` 存储位置：

```bash
export MISAKA_DATA_DIR=/path/to/custom/dir
```

### MCP 服务器

Misaka 会自动从以下路径读取 MCP 服务器配置：

- `~/.claude.json`
- `~/.claude/settings.json`

也可以直接在应用「插件」页面中管理服务器。

---

## 🛠 开发指南

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查（Ruff）
ruff check misaka/

# 类型检查（mypy）
mypy misaka/
```

### 打包为独立可执行文件

```bash
pip install -e ".[build]"
pyinstaller misaka.spec
```

---

## 🏗 架构设计

Misaka 遵循清晰的分层架构，配合依赖注入：

```
UI 层  →  State（状态）  →  Services（服务）  →  数据库 / 外部 API
```

- **`ServiceContainer`** — 启动时实例化一次，持有所有服务单例
- **`AppState`** — 响应式状态对象，贯穿整个 UI 组件树
- **`DatabaseBackend`** — 可插拔后端（默认 SQLite，可选 SeekDB）
- **`ClaudeService`** — 封装 `claude-agent-sdk`，处理流式输出、MCP 集成与权限控制

完整架构设计文档见：[`docs/plans/2026-02-23-architecture-design.md`](docs/plans/2026-02-23-architecture-design.md)

---

## 📦 主要依赖

| 包名 | 用途 |
|---|---|
| `flet >= 0.27` | 基于 Flutter 的跨平台 UI 框架 |
| `claude-agent-sdk >= 0.1.5` | 官方 Claude Code Agent 集成 SDK |
| `Pygments >= 2.18` | 代码块语法高亮 |
| `watchdog >= 4.0` | 文件系统事件监听 |
| `aiofiles >= 24.0` | 异步文件 I/O |
| `anyio >= 4.0` | 异步并发原语 |

---

## 📄 许可证

[MIT](LICENSE)
