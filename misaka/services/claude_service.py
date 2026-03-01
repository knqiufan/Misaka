"""
Claude Agent SDK integration service.

Wraps the ``claude-agent-sdk`` Python package to provide streaming
chat functionality with permission handling, MCP server support,
and environment variable management.

Uses ``ClaudeSDKClient`` for bidirectional, stateful conversations
that support multi-turn dialog, interrupts, and dynamic permission
mode changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from misaka.config import IS_WINDOWS, SettingKeys, get_expanded_path
from misaka.db.database import DatabaseBackend
from misaka.db.models import ApiProvider
from misaka.services.permission_service import PermissionService
from misaka.utils.platform import find_claude_binary, find_git_bash

logger = logging.getLogger(__name__)


def _sanitize_env_value(value: str) -> str:
    """Remove null bytes and control characters that cause spawn errors."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)


def _sanitize_env(env: dict[str, str]) -> dict[str, str]:
    """Sanitize all values in an env dict for subprocess safety."""
    return {
        k: _sanitize_env_value(v)
        for k, v in env.items()
        if isinstance(v, str)
    }


class ClaudeService:
    """Service for interacting with Claude Code via the Agent SDK.

    Manages environment setup, SDK option construction, streaming
    message dispatch, and permission callback handling.

    Uses ``ClaudeSDKClient`` for stateful, multi-turn conversations.
    """

    def __init__(self, db: DatabaseBackend, permission_service: PermissionService | None = None) -> None:
        self._db = db
        self._permission_service = permission_service or PermissionService()
        self._client: Any = None  # ClaudeSDKClient instance
        self._is_streaming: bool = False
        self._abort_event: asyncio.Event = asyncio.Event()

    def _build_env(self, provider: ApiProvider | None = None) -> dict[str, str]:
        """Build the subprocess environment for the Claude CLI.

        Starts with os.environ, overlays provider config, and expands PATH.
        """
        env: dict[str, str] = {k: v for k, v in os.environ.items() if isinstance(v, str)}

        # Ensure HOME/USERPROFILE
        home = str(Path.home())
        env.setdefault("HOME", home)
        env.setdefault("USERPROFILE", home)
        env["PATH"] = get_expanded_path()

        # Git Bash on Windows
        if IS_WINDOWS and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
            git_bash = find_git_bash()
            if git_bash:
                env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash

        if provider and provider.api_key:
            # Clear existing ANTHROPIC_* to prevent conflicts
            for key in list(env.keys()):
                if key.startswith("ANTHROPIC_"):
                    del env[key]

            env["ANTHROPIC_AUTH_TOKEN"] = provider.api_key
            env["ANTHROPIC_API_KEY"] = provider.api_key
            if provider.base_url:
                env["ANTHROPIC_BASE_URL"] = provider.base_url

            # Apply extra_env (empty string = delete)
            for key, value in provider.parse_extra_env().items():
                if value == "":
                    env.pop(key, None)
                else:
                    env[key] = value
        else:
            # Fall back to legacy settings
            legacy_token = self._db.get_setting("anthropic_auth_token")
            legacy_base = self._db.get_setting("anthropic_base_url")
            if legacy_token:
                env["ANTHROPIC_AUTH_TOKEN"] = legacy_token
            if legacy_base:
                env["ANTHROPIC_BASE_URL"] = legacy_base

        return _sanitize_env(env)

    def _build_options(
        self,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        working_directory: str | None = None,
        sdk_session_id: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        permission_mode: str = "acceptEdits",
        provider: ApiProvider | None = None,
        can_use_tool: Any = None,
    ) -> Any:
        """Build ClaudeAgentOptions from parameters.

        Returns the options object for the SDK client. Import is deferred
        to avoid import errors when the SDK is not installed.
        """
        from claude_agent_sdk import ClaudeAgentOptions

        cwd = working_directory or str(Path.home())
        env = self._build_env(provider)

        # Check for bypass permissions setting
        skip_permissions = self._db.get_setting(SettingKeys.DANGEROUSLY_SKIP_PERMISSIONS) == "true"

        effective_permission_mode = "bypassPermissions" if skip_permissions else permission_mode

        options = ClaudeAgentOptions(
            cwd=cwd,
            system_prompt=system_prompt,
            permission_mode=effective_permission_mode,
            env=env,
            allowed_tools=[
                "Read", "Write", "Edit", "Bash", "Glob", "Grep",
                "WebFetch", "WebSearch",
            ],
            include_partial_messages=True,
            can_use_tool=can_use_tool,
        )

        if skip_permissions:
            options.allow_dangerously_skip_permissions = True

        # Resume existing session
        if sdk_session_id:
            options.resume = sdk_session_id

        if model:
            options.model = model

        if mcp_servers:
            options.mcp_servers = mcp_servers

        # Find Claude binary path
        claude_path = find_claude_binary()
        if claude_path:
            ext = os.path.splitext(claude_path)[1].lower()
            if ext in (".cmd", ".bat"):
                script_path = _resolve_script_from_cmd(claude_path)
                if script_path:
                    options.cli_path = script_path
                else:
                    logger.warning(
                        "Could not resolve .js path from .cmd wrapper: %s",
                        claude_path,
                    )
            else:
                options.cli_path = claude_path

        return options

    async def send_message(
        self,
        session_id: str,
        prompt: str,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        working_directory: str | None = None,
        sdk_session_id: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        permission_mode: str = "acceptEdits",
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[dict[str, Any]], None] | None = None,
        on_status: Callable[[dict[str, Any]], None] | None = None,
        on_result: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_permission_request: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        """Send a message to Claude and stream the response.

        Uses ``ClaudeSDKClient`` for bidirectional communication.
        Callbacks are invoked as messages arrive from the SDK.
        This is a coroutine that runs until the response is complete.
        """
        from claude_agent_sdk import (
            ClaudeSDKClient,
            ClaudeSDKError,
            CLINotFoundError,
            CLIConnectionError,
            ProcessError,
        )

        self._is_streaming = True
        self._abort_event.clear()

        # Get active provider
        provider = self._db.get_active_provider()

        can_use_tool = None
        if on_permission_request:
            can_use_tool = self._make_permission_callback(on_permission_request)

        options = self._build_options(
            model=model,
            system_prompt=system_prompt,
            working_directory=working_directory,
            sdk_session_id=sdk_session_id,
            mcp_servers=mcp_servers,
            permission_mode=permission_mode,
            provider=provider,
            can_use_tool=can_use_tool,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                self._client = client

                # SDK >= 0.1.39: query() then receive_response()
                # Older SDK versions may still expose send_message().
                if hasattr(client, "query") and hasattr(client, "receive_response"):
                    await client.query(prompt, session_id=session_id)
                    response_stream = client.receive_response()
                else:
                    response_stream = client.send_message(prompt, can_use_tool=can_use_tool)

                async for message in response_stream:
                    if not self._is_streaming or self._abort_event.is_set():
                        break

                    self._dispatch_message(
                        message,
                        on_text=on_text,
                        on_tool_use=on_tool_use,
                        on_tool_result=on_tool_result,
                        on_status=on_status,
                        on_result=on_result,
                    )

        except CLINotFoundError:
            error_msg = (
                "Claude Code CLI not found. Please install it with:\n"
                "npm install -g @anthropic-ai/claude-code"
            )
            logger.error(error_msg)
            if on_error:
                on_error(error_msg)

        except CLIConnectionError as exc:
            error_msg = f"Failed to connect to Claude: {exc}"
            logger.error(error_msg, exc_info=True)
            if on_error:
                on_error(error_msg)

        except ProcessError as exc:
            error_msg = f"Claude process error: {exc}"
            logger.error(error_msg, exc_info=True)
            if on_error:
                on_error(error_msg)

        except ClaudeSDKError as exc:
            error_msg = f"SDK error: {exc}"
            logger.error(error_msg, exc_info=True)
            if on_error:
                on_error(error_msg)

        except asyncio.CancelledError:
            logger.info("send_message cancelled for session %s", session_id)

        except Exception as exc:
            error_msg = f"Unexpected error: {exc}"
            logger.error("ClaudeService.send_message error: %s", exc, exc_info=True)
            if on_error:
                on_error(error_msg)

        finally:
            self._is_streaming = False
            self._client = None

    def _make_permission_callback(
        self,
        on_permission_request: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Create the ``can_use_tool`` callback for the SDK.

        The callback forwards permission requests to the UI via
        ``on_permission_request`` and waits for the user's decision.
        """
        permission_service = self._permission_service

        async def _can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            context: Any = None,
        ) -> Any:
            from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

            permission_id = f"perm-{int(time.time() * 1000)}-{os.urandom(3).hex()}"

            # Register pending permission (returns a Future)
            future = permission_service.register(permission_id, tool_input)

            # Notify the UI about the permission request
            on_permission_request({
                "permission_id": permission_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "suggestions": getattr(context, "suggestions", None) if context else None,
            })

            # Wait for user decision
            try:
                decision = await future
            except asyncio.CancelledError:
                return PermissionResultDeny(message="Permission request cancelled")

            behavior = decision.get("behavior", "deny")
            if behavior == "allow":
                updated_input = decision.get("updatedInput", tool_input)
                return PermissionResultAllow(updated_input=updated_input)
            else:
                reason = decision.get("message", "User denied permission")
                return PermissionResultDeny(message=reason)

        return _can_use_tool

    def _dispatch_message(
        self,
        message: Any,
        *,
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[dict[str, Any]], None] | None = None,
        on_status: Callable[[dict[str, Any]], None] | None = None,
        on_result: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Dispatch a single SDK message to the appropriate callback."""
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                StreamEvent,
                SystemMessage,
                UserMessage,
            )
        except Exception:
            AssistantMessage = ResultMessage = StreamEvent = SystemMessage = UserMessage = None

        if AssistantMessage and isinstance(message, AssistantMessage):
            self._handle_assistant_message(message, on_text=on_text, on_tool_use=on_tool_use)
            return
        if UserMessage and isinstance(message, UserMessage):
            self._handle_user_message(message, on_tool_result=on_tool_result)
            return
        if ResultMessage and isinstance(message, ResultMessage):
            self._handle_result_message(message, on_result=on_result)
            return
        if SystemMessage and isinstance(message, SystemMessage):
            self._handle_system_message(message, on_status=on_status)
            return
        if StreamEvent and isinstance(message, StreamEvent):
            self._handle_stream_event(message, on_text=on_text)
            return

        msg_type = getattr(message, "type", None)

        if msg_type == "assistant":
            self._handle_assistant_message(message, on_text=on_text, on_tool_use=on_tool_use)

        elif msg_type == "user":
            self._handle_user_message(message, on_tool_result=on_tool_result)

        elif msg_type == "result":
            self._handle_result_message(message, on_result=on_result)

        elif msg_type == "system":
            self._handle_system_message(message, on_status=on_status)

        elif msg_type == "stream_event":
            self._handle_stream_event(message, on_text=on_text)

        elif msg_type == "tool_progress":
            self._handle_tool_progress(message, on_status=on_status)

    def _handle_assistant_message(
        self,
        message: Any,
        *,
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Handle an AssistantMessage from the SDK."""
        content = getattr(message, "content", None)
        if content is None:
            msg_content = getattr(message, "message", None)
            content = getattr(msg_content, "content", []) if msg_content else []

        try:
            from claude_agent_sdk import TextBlock, ToolUseBlock
        except Exception:
            TextBlock = ToolUseBlock = None

        for block in content:
            if TextBlock and isinstance(block, TextBlock) and on_text:
                if block.text:
                    on_text(block.text)
                continue
            if ToolUseBlock and isinstance(block, ToolUseBlock) and on_tool_use:
                on_tool_use({"id": block.id, "name": block.name, "input": block.input})
                continue

            block_type = getattr(block, "type", None)
            if isinstance(block, dict):
                block_type = block.get("type", block_type)
            if block_type == "text" and on_text:
                text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
                if text:
                    on_text(text)
            elif block_type == "tool_use" and on_tool_use:
                on_tool_use({
                    "id": block.get("id", "") if isinstance(block, dict) else getattr(block, "id", ""),
                    "name": block.get("name", "") if isinstance(block, dict) else getattr(block, "name", ""),
                    "input": block.get("input", {}) if isinstance(block, dict) else getattr(block, "input", {}),
                })

    def _handle_user_message(
        self,
        message: Any,
        *,
        on_tool_result: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Handle a UserMessage (tool results) from the SDK."""
        if not on_tool_result:
            return

        content = getattr(message, "content", None)
        if content is None:
            msg_content = getattr(message, "message", None)
            content = getattr(msg_content, "content", []) if msg_content else []
        if isinstance(content, str) or not isinstance(content, list):
            return

        try:
            from claude_agent_sdk import ToolResultBlock
        except Exception:
            ToolResultBlock = None

        for block in content:
            if ToolResultBlock and isinstance(block, ToolResultBlock):
                block_content = block.content
                if isinstance(block_content, list):
                    texts = []
                    for c in block_content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            texts.append(c.get("text", ""))
                    block_content = "\n".join(texts)
                elif block_content is None:
                    block_content = ""
                elif not isinstance(block_content, str):
                    block_content = str(block_content) if block_content else ""

                on_tool_result({
                    "tool_use_id": block.tool_use_id,
                    "content": block_content,
                    "is_error": bool(block.is_error),
                })
                continue

            block_type = getattr(block, "type", None)
            if isinstance(block, dict):
                block_type = block.get("type", block_type)
            if block_type == "tool_result":
                block_content = block.get("content", "") if isinstance(block, dict) else getattr(block, "content", "")
                if isinstance(block_content, list):
                    texts = []
                    for c in block_content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            texts.append(c.get("text", ""))
                    block_content = "\n".join(texts)
                elif not isinstance(block_content, str):
                    block_content = str(block_content) if block_content else ""

                on_tool_result({
                    "tool_use_id": block.get("tool_use_id", "") if isinstance(block, dict) else getattr(block, "tool_use_id", ""),
                    "content": block_content,
                    "is_error": block.get("is_error", False) if isinstance(block, dict) else getattr(block, "is_error", False),
                })

    def _handle_result_message(
        self,
        message: Any,
        *,
        on_result: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Handle a ResultMessage from the SDK."""
        if not on_result:
            return

        usage = getattr(message, "usage", None)
        token_usage = None
        if usage:
            usage_get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
            token_usage = {
                "input_tokens": usage_get("input_tokens", 0),
                "output_tokens": usage_get("output_tokens", 0),
                "cache_read_input_tokens": usage_get("cache_read_input_tokens", 0),
                "cache_creation_input_tokens": usage_get("cache_creation_input_tokens", 0),
                "cost_usd": getattr(message, "total_cost_usd", None),
            }

        on_result({
            "session_id": getattr(message, "session_id", ""),
            "subtype": getattr(message, "subtype", ""),
            "is_error": getattr(message, "is_error", False),
            "num_turns": getattr(message, "num_turns", 0),
            "duration_ms": getattr(message, "duration_ms", 0),
            "usage": token_usage,
        })

    def _handle_system_message(
        self,
        message: Any,
        *,
        on_status: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Handle a SystemMessage from the SDK."""
        if not on_status:
            return

        subtype = getattr(message, "subtype", "")
        data: dict[str, Any] = {"type": "system", "subtype": subtype}
        payload = getattr(message, "data", {}) or {}

        if subtype == "init":
            data["session_id"] = payload.get("session_id", getattr(message, "session_id", ""))
            data["model"] = payload.get("model", getattr(message, "model", ""))
            data["tools"] = payload.get("tools", getattr(message, "tools", []))

        on_status(data)

    def _handle_stream_event(
        self,
        message: Any,
        *,
        on_text: Callable[[str], None] | None = None,
    ) -> None:
        """Handle a partial/stream event for real-time text updates."""
        if not on_text:
            return

        event = getattr(message, "event", None)
        if event is None:
            return

        event_type = event.get("type", "") if isinstance(event, dict) else getattr(event, "type", "")
        if event_type == "content_block_delta":
            delta = event.get("delta", None) if isinstance(event, dict) else getattr(event, "delta", None)
            if delta:
                delta_type = delta.get("type", "") if isinstance(delta, dict) else getattr(delta, "type", "")
                if delta_type == "text_delta":
                    text = delta.get("text", "") if isinstance(delta, dict) else getattr(delta, "text", "")
                    if text:
                        on_text(text)

    def _handle_tool_progress(
        self,
        message: Any,
        *,
        on_status: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Handle a tool progress message."""
        if not on_status:
            return

        on_status({
            "type": "tool_progress",
            "tool_use_id": getattr(message, "tool_use_id", ""),
            "tool_name": getattr(message, "tool_name", ""),
            "elapsed_time_seconds": getattr(message, "elapsed_time_seconds", 0),
        })

    async def abort(self) -> None:
        """Abort the current streaming operation."""
        self._is_streaming = False
        self._abort_event.set()

        if self._client:
            try:
                if hasattr(self._client, "abort"):
                    await self._client.abort()
                elif hasattr(self._client, "interrupt"):
                    await self._client.interrupt()
            except Exception as exc:
                logger.warning("Error aborting client: %s", exc)
            self._client = None

    @property
    def is_streaming(self) -> bool:
        """Whether a streaming operation is currently in progress."""
        return self._is_streaming


def _resolve_script_from_cmd(cmd_path: str) -> str | None:
    """Parse a Windows .cmd wrapper to extract the real .js script path.

    npm installs CLI tools as .cmd wrappers on Windows that cannot be
    spawned without ``shell=True``. This extracts the underlying .js
    script path so it can be passed to the SDK directly.
    """
    try:
        content = Path(cmd_path).read_text(encoding="utf-8", errors="ignore")
        cmd_dir = str(Path(cmd_path).parent)

        patterns = [
            r'"%~dp0\\([^"]*claude[^"]*\.js)"',
            r"%~dp0\\(\S*claude\S*\.js)",
            r'"%dp0%\\([^"]*claude[^"]*\.js)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                resolved = os.path.normpath(os.path.join(cmd_dir, match.group(1)))
                if os.path.isfile(resolved):
                    return resolved
    except OSError:
        pass
    return None
