# Claude Agent SDK 实战指南：从第一性原理到生产级应用

## 一、前言：什么是 Claude Agent SDK？

Claude Agent SDK（`claude-agent-sdk`）是 Anthropic 官方提供的 Python SDK，用于构建与 Claude Code CLI 交互的应用程序。它不是一个简单的 HTTP API 封装，而是一个**双向通信框架**，支持：

- **流式对话**：实时接收 Claude 的响应
- **工具调用权限管理**：在 Claude 执行工具前请求用户批准
- **多轮会话持久化**：支持会话恢复和继续
- **MCP 服务器集成**：扩展 Claude 的能力边界

本文将以开源项目 **Misaka**（一个 Claude Code 桌面 GUI 客户端）为例，深入剖析 SDK 的实战用法。

## 二、第一性原理：SDK 的底层架构

### 2.1 核心通信模型

```
┌─────────────────────────────────────────────────────────────┐
│                     Python Application                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  ClaudeSDKClient                         │ │
│  │   (Async Context Manager + Message Stream)               │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            ↕ JSON-RPC over stdio              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Claude Code CLI (Node.js)                   │ │
│  │   (@anthropic-ai/claude-code)                            │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            ↕ Anthropic API                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Claude Model                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

SDK 的本质是：**Python 通过 stdio 与 Claude CLI 子进程通信，CLI 负责与 Anthropic API 交互**。这种架构的优势：

1. **解耦**：CLI 处理 API 认证、重试、协议细节
2. **可扩展**：CLI 可以执行本地工具（读写文件、运行命令）
3. **一致性**：与命令行使用相同的后端逻辑

### 2.2 依赖安装

```toml
# pyproject.toml
[project]
dependencies = [
    "claude-agent-sdk>=0.1.5",
]
```

外部运行时要求：
```bash
# 安装 Claude Code CLI
npm install -g @anthropic-ai/claude-code
```

## 三、核心 API 详解

### 3.1 ClaudeAgentOptions - 配置一切

`ClaudeAgentOptions` 是 SDK 的配置中心，控制 Claude 的行为：

```python
from claude_agent_sdk import ClaudeAgentOptions

options = ClaudeAgentOptions(
    # 工作目录 - Claude 的文件操作基准路径
    cwd="/path/to/project",

    # 系统提示词 - 覆盖默认行为
    system_prompt="You are a helpful coding assistant.",

    # 权限模式 - 控制工具调用策略
    # - "default": 每次工具调用都请求权限
    # - "plan": 规划模式，不执行工具
    # - "bypassPermissions": 跳过所有权限检查（危险！）
    permission_mode="default",

    # 子进程环境变量
    env={"ANTHROPIC_API_KEY": "sk-..."},

    # 允许的工具列表（空 = 使用 permission_mode 控制）
    allowed_tools=[],

    # 禁用的工具列表
    disallowed_tools=["Bash", "Write"],

    # 启用部分消息流式传输
    include_partial_messages=True,

    # 恢复已有会话
    resume="sdk-session-id-123",

    # 指定模型
    model="claude-sonnet-4-5",

    # MCP 服务器配置
    mcp_servers={
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@anthropic/fs-mcp"],
        }
    },

    # CLI 路径（自动发现或手动指定）
    cli_path="/usr/local/bin/claude",

    # 跳过权限检查（配合 bypassPermissions）
    allow_dangerously_skip_permissions=True,
)
```

#### 实战技巧：环境变量构建

Claude CLI 子进程需要正确的环境变量才能工作：

```python
import os
from pathlib import Path

def build_claude_env(db, provider=None) -> dict[str, str]:
    """构建 Claude CLI 子进程环境"""
    # 1. 继承当前环境
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}

    # 2. 确保 HOME 存在
    home = str(Path.home())
    env.setdefault("HOME", home)

    # 3. 注入 API 凭据
    if provider and provider.api_key:
        env["ANTHROPIC_AUTH_TOKEN"] = provider.api_key
        env["ANTHROPIC_API_KEY"] = provider.api_key
        if provider.base_url:
            env["ANTHROPIC_BASE_URL"] = provider.base_url

    # 4. Windows 特殊处理：Git Bash 路径
    if IS_WINDOWS:
        git_bash = find_git_bash()
        if git_bash:
            env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash

    return env
```

### 3.2 ClaudeSDKClient - 核心客户端

`ClaudeSDKClient` 是 SDK 的主入口，使用异步上下文管理器模式：

```python
from claude_agent_sdk import ClaudeSDKClient

async with ClaudeSDKClient(options=options) as client:
    # 方式 1：新版 API (SDK >= 0.1.39)
    await client.query(prompt, session_id=session_id)
    response_stream = client.receive_response()

    # 方式 2：旧版 API
    # response_stream = client.send_message(prompt, can_use_tool=callback)

    async for message in response_stream:
        # 处理消息...
        pass
```

**关键设计点**：

1. **Async Context Manager**：确保资源正确释放
2. **Async Iterator**：流式接收消息
3. **双向通信**：可以中断正在进行的操作

#### 版本兼容处理

```python
# SDK 版本兼容：新版使用 query+receive_response，旧版使用 send_message
if hasattr(client, "query") and hasattr(client, "receive_response"):
    await client.query(prompt, session_id=session_id)
    response_stream = client.receive_response()
else:
    response_stream = client.send_message(prompt, can_use_tool=can_use_tool)
```

### 3.3 消息类型系统

SDK 返回多种消息类型，需要分别处理：

```python
from claude_agent_sdk import (
    AssistantMessage,
    UserMessage,
    ResultMessage,
    SystemMessage,
)
from claude_agent_sdk.types import StreamEvent

def dispatch_message(message):
    """分发消息到对应的处理器"""

    # 1. Assistant 消息：Claude 的回复
    if isinstance(message, AssistantMessage):
        handle_assistant_message(message)

    # 2. User 消息：工具执行结果（Echo 回来）
    elif isinstance(message, UserMessage):
        handle_user_message(message)

    # 3. Result 消息：会话结束，包含 token 使用量
    elif isinstance(message, ResultMessage):
        handle_result_message(message)

    # 4. System 消息：初始化信息
    elif isinstance(message, SystemMessage):
        handle_system_message(message)

    # 5. Stream Event：实时文本流
    elif isinstance(message, StreamEvent):
        handle_stream_event(message)
```

#### 详细消息结构

**AssistantMessage** - Claude 的回复内容：

```python
def handle_assistant_message(message):
    content = message.content  # List[ContentBlock]

    for block in content:
        if isinstance(block, TextBlock):
            # 文本块
            print(block.text)

        elif isinstance(block, ToolUseBlock):
            # 工具调用请求
            print(f"Tool: {block.name}")
            print(f"Input: {block.input}")
            print(f"ID: {block.id}")
```

**ResultMessage** - 会话结束摘要：

```python
def handle_result_message(message):
    # 会话 ID（用于恢复）
    session_id = message.session_id

    # 是否成功
    is_error = message.is_error

    # Token 使用统计
    usage = message.usage
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    cache_read = usage.cache_read_input_tokens

    # 费用（美元）
    cost = message.total_cost_usd

    # 对话轮数
    turns = message.num_turns

    # 耗时
    duration_ms = message.duration_ms
```

**StreamEvent** - 实时文本流：

```python
def handle_stream_event(message):
    event = message.event

    if event.type == "content_block_delta":
        delta = event.delta
        if delta.type == "text_delta":
            # 实时文本片段
            print(delta.text, end="", flush=True)
```

### 3.4 权限回调机制

这是 SDK 最强大的特性之一：**在 Claude 执行工具前请求用户批准**。

```python
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

async def can_use_tool(
    tool_name: str,
    tool_input: dict,
    context: Any = None,
) -> PermissionResultAllow | PermissionResultDeny:
    """权限回调函数"""

    # 1. 自动批准白名单工具
    if tool_name in {"Read", "Glob", "Grep"}:
        return PermissionResultAllow(updated_input=tool_input)

    # 2. 显示 UI 让用户决定
    decision = await show_permission_dialog(tool_name, tool_input)

    if decision.behavior == "allow":
        # 可选：修改工具输入
        updated = decision.get("updatedInput", tool_input)
        return PermissionResultAllow(updated_input=updated)
    else:
        return PermissionResultDeny(message=decision.message)

# 将回调传递给 options
options.can_use_tool = can_use_tool
```

#### 权限服务设计模式

```python
class PermissionService:
    """管理待处理的权限请求"""

    def __init__(self):
        self._pending: dict[str, PendingPermission] = {}

    def register(self, permission_id: str, tool_input: dict) -> asyncio.Future:
        """注册一个待处理的权限请求，返回 Future"""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[permission_id] = PendingPermission(
            future=future,
            tool_input=tool_input,
        )
        return future

    def resolve(self, permission_id: str, decision: dict) -> bool:
        """用户做出决定后，解析 Future"""
        entry = self._pending.pop(permission_id, None)
        if entry and not entry.future.done():
            entry.future.set_result(decision)
            return True
        return False

# 在权限回调中使用
async def can_use_tool(tool_name, tool_input, context):
    permission_id = f"perm-{time.time_ns()}"
    future = permission_service.register(permission_id, tool_input)

    # 通知 UI 显示权限对话框
    on_permission_request({
        "permission_id": permission_id,
        "tool_name": tool_name,
        "tool_input": tool_input,
    })

    # 等待用户决定
    decision = await future

    if decision["behavior"] == "allow":
        return PermissionResultAllow(updated_input=decision.get("updatedInput", tool_input))
    return PermissionResultDeny(message=decision.get("message", "Denied"))
```

## 四、完整实战示例

### 4.1 基础聊天服务

```python
class ClaudeService:
    """Claude Agent SDK 封装服务"""

    def __init__(self, db, permission_service):
        self._db = db
        self._permission_service = permission_service
        self._active_streams: dict[str, bool] = {}
        self._clients: dict[str, Any] = {}

    async def send_message(
        self,
        session_id: str,
        prompt: str,
        *,
        model: str | None = None,
        working_directory: str | None = None,
        sdk_session_id: str | None = None,
        mcp_servers: dict | None = None,
        permission_mode: str = "default",
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[dict], None] | None = None,
        on_result: Callable[[dict], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_permission_request: Callable[[dict], Any] | None = None,
    ) -> None:
        """发送消息并流式接收响应"""

        from claude_agent_sdk import (
            ClaudeSDKClient,
            ClaudeSDKError,
            CLINotFoundError,
            CLIConnectionError,
            ProcessError,
        )

        # 标记会话正在流式传输
        self._active_streams[session_id] = True

        # 构建配置
        options = self._build_options(
            model=model,
            working_directory=working_directory,
            sdk_session_id=sdk_session_id,
            mcp_servers=mcp_servers,
            permission_mode=permission_mode,
        )

        # 如果有权限回调需求，注入 can_use_tool
        if on_permission_request:
            options.can_use_tool = self._make_permission_callback(
                on_permission_request
            )

        try:
            async with ClaudeSDKClient(options=options) as client:
                self._clients[session_id] = client

                # 发送消息
                if hasattr(client, "query"):
                    await client.query(prompt, session_id=session_id)
                    response_stream = client.receive_response()
                else:
                    response_stream = client.send_message(prompt)

                # 流式处理响应
                async for message in response_stream:
                    # 检查是否被中断
                    if session_id not in self._active_streams:
                        break

                    # 分发消息到对应回调
                    self._dispatch_message(
                        message,
                        on_text=on_text,
                        on_tool_use=on_tool_use,
                        on_result=on_result,
                    )

        except CLINotFoundError:
            if on_error:
                on_error("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")

        except CLIConnectionError as e:
            if on_error:
                on_error(f"Connection error: {e}")

        except ClaudeSDKError as e:
            if on_error:
                on_error(f"SDK error: {e}")

        finally:
            self._active_streams.pop(session_id, None)
            self._clients.pop(session_id, None)

    async def abort(self, session_id: str) -> None:
        """中断正在进行的流式传输"""
        self._active_streams.pop(session_id, None)
        client = self._clients.get(session_id)
        if client:
            if hasattr(client, "abort"):
                await client.abort()
            elif hasattr(client, "interrupt"):
                await client.interrupt()
```

### 4.2 会话恢复

```python
async def continue_conversation(session_id: str, sdk_session_id: str, new_prompt: str):
    """继续之前的对话"""

    options = ClaudeAgentOptions(
        cwd=working_directory,
        # 关键：传入之前的 sdk_session_id
        resume=sdk_session_id,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(new_prompt, session_id=sdk_session_id)
        async for message in client.receive_response():
            # 处理消息...
            pass
```

### 4.3 MCP 服务器集成

```python
# 配置 MCP 服务器
mcp_servers = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@anthropic/fs-mcp", "/path/to/allowed/dir"],
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@anthropic/github-mcp"],
        "env": {
            "GITHUB_TOKEN": "ghp_...",
        },
    },
}

options = ClaudeAgentOptions(
    cwd=working_directory,
    mcp_servers=mcp_servers,
)
```

## 五、错误处理最佳实践

### 5.1 异常层次结构

```
ClaudeSDKError (基类)
├── CLINotFoundError    # CLI 未安装
├── CLIConnectionError  # 无法连接到 CLI
└── ProcessError        # CLI 进程异常退出
```

### 5.2 完整错误处理

```python
from claude_agent_sdk import (
    ClaudeSDKError,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
)

try:
    async with ClaudeSDKClient(options=options) as client:
        # ...

except CLINotFoundError:
    # 引导用户安装 CLI
    print("Please install Claude CLI:")
    print("npm install -g @anthropic-ai/claude-code")

except CLIConnectionError as e:
    # 连接问题，可能是 CLI 崩溃
    print(f"Failed to connect: {e}")
    # 可以尝试重启

except ProcessError as e:
    # CLI 进程异常退出
    print(f"CLI crashed: {e}")
    # 检查 CLI 版本兼容性

except ClaudeSDKError as e:
    # 其他 SDK 错误
    print(f"SDK error: {e}")

except asyncio.CancelledError:
    # 用户取消了操作
    print("Operation cancelled")

except Exception as e:
    # 未预期的错误
    logger.exception("Unexpected error")
```

## 六、性能优化技巧

### 6.1 流式 UI 刷新节流

```python
import time

class ThrottledUI:
    """节流 UI 刷新，避免过于频繁的渲染"""

    def __init__(self, refresh_callback, min_interval: float = 0.033):
        self._refresh = refresh_callback
        self._min_interval = min_interval  # ~30fps
        self._last_refresh = 0.0
        self._pending = False

    def request_refresh(self):
        now = time.monotonic()
        elapsed = now - self._last_refresh

        if elapsed >= self._min_interval:
            self._last_refresh = now
            self._refresh()
        elif not self._pending:
            self._pending = True
            # 延迟刷新
            asyncio.get_event_loop().call_later(
                self._min_interval - elapsed,
                self._do_refresh,
            )

    def _do_refresh(self):
        self._pending = False
        self._last_refresh = time.monotonic()
        self._refresh()
```

### 6.2 避免重复输出

SDK 会同时发送 `StreamEvent`（部分文本）和 `AssistantMessage`（完整文本）。需要避免重复：

```python
class ClaudeService:
    def __init__(self):
        self._saw_text_delta_in_turn = False

    def _handle_stream_event(self, message, on_text):
        """处理流式事件"""
        if message.event.type == "content_block_delta":
            delta = message.event.delta
            if delta.type == "text_delta":
                self._saw_text_delta_in_turn = True
                on_text(delta.text)

    def _handle_assistant_message(self, message, on_text):
        """处理完整消息"""
        for block in message.content:
            if isinstance(block, TextBlock):
                # 如果已经收到过流式文本，跳过完整文本
                if self._saw_text_delta_in_turn:
                    continue
                on_text(block.text)
```

## 七、平台特定注意事项

### 7.1 Windows 平台

```python
# Windows 上需要特殊处理：
# 1. CLI 可能是 .cmd 包装器
# 2. 需要指定 Git Bash 路径
# 3. 需要扩展 PATH 以找到 npm 全局安装

def find_claude_binary() -> str | None:
    """查找 Claude CLI 二进制文件"""
    home = str(Path.home())

    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        local_appdata = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        candidates = [
            os.path.join(appdata, "npm", "claude.cmd"),
            os.path.join(local_appdata, "npm", "claude.cmd"),
            os.path.join(home, ".npm-global", "bin", "claude.cmd"),
        ]
    else:
        candidates = [
            "/usr/local/bin/claude",
            "/opt/homebrew/bin/claude",
            os.path.join(home, ".local", "bin", "claude"),
        ]

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None
```

### 7.2 环境变量清理

```python
import re

def _sanitize_env_value(value: str) -> str:
    """移除可能导致子进程启动失败的空字节和控制字符"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

def _sanitize_env(env: dict[str, str]) -> dict[str, str]:
    """清理环境变量字典"""
    return {
        k: _sanitize_env_value(v)
        for k, v in env.items()
        if isinstance(v, str)
    }
```

## 八、API 速查表

### 8.1 核心类

| 类名 | 用途 | 关键方法 |
|------|------|----------|
| `ClaudeSDKClient` | 主客户端 | `query()`, `receive_response()`, `abort()` |
| `ClaudeAgentOptions` | 配置选项 | 所有配置属性 |
| `AssistantMessage` | Claude 回复 | `.content` (List[ContentBlock]) |
| `ResultMessage` | 会话结果 | `.session_id`, `.usage`, `.total_cost_usd` |
| `SystemMessage` | 系统信息 | `.subtype` ("init"), `.session_id` |
| `StreamEvent` | 流式事件 | `.event.type`, `.event.delta` |

### 8.2 权限相关

| 类/函数 | 用途 |
|---------|------|
| `PermissionResultAllow` | 批准工具调用 |
| `PermissionResultDeny` | 拒绝工具调用 |
| `can_use_tool` 回调 | 权限决策函数 |

### 8.3 错误类型

| 异常 | 触发条件 |
|------|----------|
| `CLINotFoundError` | CLI 未安装 |
| `CLIConnectionError` | 无法连接 CLI |
| `ProcessError` | CLI 进程崩溃 |
| `ClaudeSDKError` | 其他 SDK 错误 |

## 九、总结

Claude Agent SDK 的核心设计理念：

| 特性 | 设计模式 | 实战要点 |
|------|----------|----------|
| 通信模型 | stdio JSON-RPC | 子进程管理，注意资源释放 |
| 配置管理 | Options 对象 | 环境变量、权限模式、MCP 服务器 |
| 消息流 | Async Iterator | 流式处理，支持中断 |
| 权限控制 | Callback + Future | 异步等待用户决策 |
| 会话持久化 | session_id | 恢复对话上下文 |

**最佳实践清单**：

1. ✅ 始终使用 `async with` 管理 Client 生命周期
2. ✅ 正确处理所有消息类型
3. ✅ 实现权限回调以控制工具执行
4. ✅ 捕获所有 SDK 异常类型
5. ✅ 节流 UI 刷新避免性能问题
6. ✅ 处理流式和完整消息的去重
7. ✅ Windows 平台特殊处理 CLI 路径和 Git Bash
8. ✅ 清理环境变量中的控制字符

---

*本文基于 Misaka 项目（Claude Code 桌面 GUI 客户端）的实战经验编写。*

**参考资料**：
- [Claude Agent SDK PyPI](https://pypi.org/project/claude-agent-sdk/)
- [Claude Code CLI](https://www.npmjs.com/package/@anthropic-ai/claude-code)
- [Misaka 源码](./misaka/services/chat/claude_service.py)
