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
import contextlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from misaka.config import SettingKeys
from misaka.db.database import DatabaseBackend
from misaka.services.common.claude_env_builder import build_claude_env
from misaka.services.chat.permission_service import PermissionService
from misaka.utils.platform import find_claude_sdk_binary

logger = logging.getLogger(__name__)


def _battr(block: Any, key: str, default: Any = "") -> Any:
    """Get attribute from a block that may be a dict or an object."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


class ClaudeService:
    """Service for interacting with Claude Code via the Agent SDK.

    Manages environment setup, SDK option construction, streaming
    message dispatch, and permission callback handling.

    Uses ``ClaudeSDKClient`` for stateful, multi-turn conversations.
    """

    def __init__(
        self,
        db: DatabaseBackend,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._db = db
        self._permission_service = permission_service or PermissionService()
        # Per-session streaming state (keyed by session_id)
        self._active_streams: dict[str, bool] = {}
        self._clients: dict[str, Any] = {}
        self._abort_events: dict[str, asyncio.Event] = {}
        self._debug_log_enabled: bool = False
        self._saw_text_delta_in_turn: bool = False

    def _is_debug_log_enabled(self) -> bool:
        """Return whether Claude SDK debug logging is enabled.

        Enabled via environment variable MISAKA_CLAUDE_DEBUG_LOG=true
        or via config file (~/.misaka/config.json).
        """
        # Check environment variable first
        if os.environ.get("MISAKA_CLAUDE_DEBUG_LOG", "").lower() == "true":
            return True
        # Check config file
        config_path = Path.home() / ".misaka" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                if config.get("claude_debug_log", False):
                    return True
            except (json.JSONDecodeError, OSError):
                pass
        return False

    def _debug_log(self, message: str, *args: Any) -> None:
        """Write concise Claude SDK debug logs when enabled."""
        if self._debug_log_enabled:
            logger.info("[ClaudeSDK] " + message, *args)

    def _build_env(self) -> dict[str, str]:
        """Build the subprocess environment for the Claude CLI."""
        return build_claude_env(self._db)

    def _build_options(
        self,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        working_directory: str | None = None,
        sdk_session_id: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        session_mode: str = "agent",
        permission_mode: str = "default",
        can_use_tool: Any = None,
    ) -> Any:
        """Build ClaudeAgentOptions from parameters.

        Returns the options object for the SDK client. Import is deferred
        to avoid import errors when the SDK is not installed.

        Handles session_mode to determine SDK permission behavior:
        - "plan": SDK native plan mode, no tool execution
        - "ask": read-only, disallows Write/Edit/Bash
        - "agent": uses permission_mode setting
        """
        from claude_agent_sdk import ClaudeAgentOptions

        cwd = working_directory or str(Path.home())
        env = self._build_env()

        # Check for bypass permissions setting
        skip_permissions = self._db.get_setting(SettingKeys.DANGEROUSLY_SKIP_PERMISSIONS) == "true"

        # Determine final SDK permission_mode and disallowed_tools based on session_mode
        final_permission_mode: str
        final_disallowed_tools: list[str] | None = None
        final_can_use_tool: Any = None

        if skip_permissions:
            final_permission_mode = "bypassPermissions"
        elif session_mode == "plan":
            # Plan mode: SDK native, no tool execution
            final_permission_mode = "plan"
        elif session_mode == "ask":
            # Ask mode: read-only, disallow write tools
            final_permission_mode = "default"
            final_disallowed_tools = ["Write", "Edit", "Bash"]
            final_can_use_tool = can_use_tool
        else:
            # Agent mode: use permission_mode setting
            final_permission_mode = permission_mode
            final_can_use_tool = can_use_tool

        options = ClaudeAgentOptions(
            cwd=cwd,
            system_prompt=system_prompt,
            permission_mode=final_permission_mode,
            env=env,
            allowed_tools=[],  # Empty to let permission_mode handle access
            include_partial_messages=True,
            can_use_tool=final_can_use_tool,
            disallowed_tools=final_disallowed_tools,
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
        claude_path = find_claude_sdk_binary()
        if claude_path:
            # SDK transport executes cli_path directly as a process.
            # On Windows, passing a resolved .js path causes WinError 193.
            # Keep the actual executable/wrapper path (e.g. claude.cmd / claude.exe).
            options.cli_path = claude_path

        return options

    async def send_message(
        self,
        session_id: str,
        prompt: str | list[dict[str, Any]],
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        working_directory: str | None = None,
        sdk_session_id: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        session_mode: str = "agent",
        permission_mode: str = "default",
        should_auto_allow: Callable[[str], bool] | None = None,
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

        Args:
            session_id: Unique identifier for the session.
            prompt: Either a text string or a list of content blocks for multimodal.
                For multimodal: [{"type": "image", ...}, {"type": "text", "text": "..."}]
            ... other args ...
        """
        from claude_agent_sdk import (
            ClaudeSDKClient,
            ClaudeSDKError,
            CLIConnectionError,
            CLINotFoundError,
            ProcessError,
        )

        self._active_streams[session_id] = True
        abort_event = asyncio.Event()
        self._abort_events[session_id] = abort_event
        self._debug_log_enabled = self._is_debug_log_enabled()
        self._saw_text_delta_in_turn = False
        message_counts: dict[str, int] = {
            "assistant": 0,
            "user": 0,
            "result": 0,
            "system": 0,
            "stream_event": 0,
            "other": 0,
        }

        can_use_tool = None
        if on_permission_request:
            can_use_tool = self._make_permission_callback(on_permission_request, should_auto_allow)

        options = self._build_options(
            model=model,
            system_prompt=system_prompt,
            working_directory=working_directory,
            sdk_session_id=sdk_session_id,
            mcp_servers=mcp_servers,
            session_mode=session_mode,
            permission_mode=permission_mode,
            can_use_tool=can_use_tool,
        )
        self._debug_log(
            "start sid=%s model=%s cwd=%s resume=%s mcp=%s",
            session_id,
            model or "(default)",
            working_directory or "(home)",
            bool(sdk_session_id),
            bool(mcp_servers),
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                self._clients[session_id] = client

                # SDK >= 0.1.39: query() then receive_response()
                # Older SDK versions may still expose send_message().
                if hasattr(client, "query") and hasattr(client, "receive_response"):
                    # SDK query() requires AsyncIterable with full message structure
                    async def _make_async_iter():
                        # Build content blocks
                        if isinstance(prompt, list):
                            content_blocks = prompt
                        else:
                            content_blocks = [{"type": "text", "text": prompt}]

                        # Yield a complete message with content blocks
                        yield {
                            "type": "user",
                            "message": {"role": "user", "content": content_blocks},
                            "parent_tool_use_id": None,
                        }

                    await client.query(_make_async_iter(), session_id=session_id)
                    response_stream = client.receive_response()
                else:
                    response_stream = client.send_message(prompt, can_use_tool=can_use_tool)

                async for message in response_stream:
                    if session_id not in self._active_streams or abort_event.is_set():
                        break
                    kind = self._classify_message_kind(message)
                    message_counts[kind] = message_counts.get(kind, 0) + 1

                    self._dispatch_message(
                        message,
                        on_text=on_text,
                        on_tool_use=on_tool_use,
                        on_tool_result=on_tool_result,
                        on_status=on_status,
                        on_result=on_result,
                    )

                # Explicitly close the async generator to prevent
                # "Task exception was never retrieved" errors when the
                # subprocess exits with a non-zero code during cleanup.
                # When user aborted, ProcessError from aclose is expected.
                if hasattr(response_stream, "aclose"):
                    try:
                        await response_stream.aclose()
                    except Exception as exc:
                        if abort_event.is_set():
                            logger.debug(
                                "Stream aclose raised during abort (expected): %s",
                                exc,
                            )
                        else:
                            logger.warning("Stream aclose raised: %s", exc)

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
            if abort_event.is_set():
                logger.info(
                    "Claude process exited during user abort (session %s): %s",
                    session_id,
                    exc,
                )
            else:
                error_msg = f"Claude process error: {exc}"
                logger.error(error_msg, exc_info=True)
                if on_error:
                    on_error(error_msg)

        except ClaudeSDKError as exc:
            if abort_event.is_set():
                logger.info(
                    "SDK error during user abort (session %s): %s",
                    session_id,
                    exc,
                )
            else:
                error_msg = f"SDK error: {exc}"
                logger.error(error_msg, exc_info=True)
                if on_error:
                    on_error(error_msg)

        except asyncio.CancelledError:
            logger.info("send_message cancelled for session %s", session_id)

        except Exception as exc:
            if abort_event.is_set():
                logger.info(
                    "Stream error during user abort (session %s): %s",
                    session_id,
                    exc,
                )
            else:
                error_msg = f"Unexpected error: {exc}"
                logger.error("ClaudeService.send_message error: %s", exc, exc_info=True)
                if on_error:
                    on_error(error_msg)

        finally:
            self._debug_log(
                "done sid=%s counts=%s",
                session_id,
                json.dumps(message_counts, ensure_ascii=False),
            )
            self._active_streams.pop(session_id, None)
            self._clients.pop(session_id, None)
            self._abort_events.pop(session_id, None)
            self._debug_log_enabled = False
            self._saw_text_delta_in_turn = False

    @staticmethod
    def _classify_message_kind(message: Any) -> str:
        """Classify SDK message into a stable, concise label."""
        name = type(message).__name__
        mapping = {
            "AssistantMessage": "assistant",
            "UserMessage": "user",
            "ResultMessage": "result",
            "SystemMessage": "system",
            "StreamEvent": "stream_event",
        }
        return mapping.get(name, "other")

    def _make_permission_callback(
        self,
        on_permission_request: Callable[[dict[str, Any]], Any],
        should_auto_allow: Callable[[str], bool] | None = None,
    ) -> Any:
        """Create the ``can_use_tool`` callback for the SDK.

        The callback forwards permission requests to the UI via
        ``on_permission_request`` and waits for the user's decision.
        If ``should_auto_allow`` is provided, it is checked first and
        auto-approves matching tools without showing a UI dialog.
        """
        permission_service = self._permission_service

        async def _can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            context: Any = None,
        ) -> Any:
            from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

            # Check auto-allow FIRST — before registering a Future
            if should_auto_allow and should_auto_allow(tool_name):
                return PermissionResultAllow(updated_input=tool_input)

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
        AssistantMessage = ResultMessage = SystemMessage = UserMessage = None
        StreamEvent = None
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                SystemMessage,
                UserMessage,
            )
        except (ImportError, AttributeError):
            pass
        try:
            from claude_agent_sdk.types import StreamEvent
        except (ImportError, AttributeError):
            pass

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
        else:
            self._debug_log("unhandled message type=%s class=%s", msg_type, type(message).__name__)

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
            from claude_agent_sdk.types import TextBlock, ToolUseBlock, ThinkingBlock
        except (ImportError, AttributeError):
            TextBlock = ToolUseBlock = ThinkingBlock = None

        for block in content:
            # Skip ThinkingBlock (extended thinking) - internal reasoning, not user output
            if ThinkingBlock and isinstance(block, ThinkingBlock):
                continue
            block_type = getattr(block, "type", None)
            if isinstance(block, dict) and block_type is None:
                block_type = block.get("type")
            if block_type == "thinking":
                continue

            if TextBlock and isinstance(block, TextBlock) and on_text:
                if self._saw_text_delta_in_turn:
                    # Prevent duplicate output: when partial text deltas were already streamed,
                    # assistant full text blocks would repeat the same content.
                    continue
                if block.text:
                    on_text(block.text)
                continue
            if ToolUseBlock and isinstance(block, ToolUseBlock) and on_tool_use:
                on_tool_use({"id": block.id, "name": block.name, "input": block.input})
                continue

            if block_type == "text" and on_text:
                if self._saw_text_delta_in_turn:
                    continue
                text = _battr(block, "text", "")
                if text:
                    on_text(text)
            elif block_type == "tool_use" and on_tool_use:
                on_tool_use({
                    "id": _battr(block, "id", ""),
                    "name": _battr(block, "name", ""),
                    "input": _battr(block, "input", {}),
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
            from claude_agent_sdk.types import ToolResultBlock
        except (ImportError, AttributeError):
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
                block_content = _battr(block, "content", "")
                if isinstance(block_content, list):
                    texts = []
                    for c in block_content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            texts.append(c.get("text", ""))
                    block_content = "\n".join(texts)
                elif not isinstance(block_content, str):
                    block_content = str(block_content) if block_content else ""

                on_tool_result({
                    "tool_use_id": _battr(block, "tool_use_id", ""),
                    "content": block_content,
                    "is_error": _battr(block, "is_error", False),
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
            def usage_get(k: str, d: Any = 0) -> Any:
                return _battr(usage, k, d)
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
        """Handle a partial/stream event for real-time text updates.

        Supports content_block_delta with text_delta. Skips thinking_block_delta
        (extended thinking) as it is internal reasoning. Event may be dict or object.
        """
        if not on_text:
            return

        event = getattr(message, "event", None)
        if event is None:
            return

        event_type = _battr(event, "type", "")
        if event_type != "content_block_delta":
            # e.g. thinking_block_delta, content_block_start - skip
            self._debug_log(
                "stream_event skip event_type=%s (waiting for content_block_delta)",
                event_type or "(empty)",
            )
            return

        delta = _battr(event, "delta", None)
        if not delta:
            return

        delta_type = _battr(delta, "type", "")
        if delta_type != "text_delta":
            # thinking_block_delta etc - skip, wait for actual text
            return

        text = _battr(delta, "text", "")
        if text:
            self._saw_text_delta_in_turn = True
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

    async def abort(self, session_id: str | None = None) -> None:
        """Abort streaming for a specific session (or the sole active session)."""
        if session_id is None:
            # Backward-compat: if only one active stream, abort it
            if len(self._active_streams) == 1:
                session_id = next(iter(self._active_streams))
            else:
                return

        self._active_streams.pop(session_id, None)
        event = self._abort_events.get(session_id)
        if event:
            event.set()

        client = self._clients.get(session_id)
        if client:
            try:
                if hasattr(client, "abort"):
                    await client.abort()
                elif hasattr(client, "interrupt"):
                    await client.interrupt()
            except Exception as exc:
                logger.warning("Error aborting client for session %s: %s", session_id, exc)
            self._clients.pop(session_id, None)

    async def abort_all(self) -> None:
        """Abort all active streaming sessions (used during shutdown)."""
        session_ids = list(self._active_streams.keys())
        for sid in session_ids:
            await self.abort(sid)

    @property
    def is_streaming(self) -> bool:
        """Whether any streaming operation is currently in progress."""
        return bool(self._active_streams)

    def is_session_streaming(self, session_id: str) -> bool:
        """Whether a specific session is currently streaming."""
        return session_id in self._active_streams


