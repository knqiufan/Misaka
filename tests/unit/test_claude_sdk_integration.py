"""
Tests for Claude SDK integration in ClaudeService.

Tests send_message streaming, permission callbacks, error handling,
and session resume with fully mocked SDK.

NOTE: The SDK types (ClaudeSDKClient, ClaudeAgentOptions, etc.) are imported
lazily inside method bodies, so we mock them at the `sys.modules` level.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import misaka.i18n
from misaka.services.chat.claude_service import ClaudeService
from misaka.services.chat.permission_service import PermissionService
from misaka.utils.platform import find_claude_sdk_binary
from misaka.services.common.claude_env_builder import _sanitize_env, _sanitize_env_value


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_i18n() -> None:
    """Ensure i18n is initialised so ErrorClassifier can format messages."""
    misaka.i18n.init("en")


@pytest.fixture
def permission_service() -> PermissionService:
    return PermissionService()


@pytest.fixture
def claude_service(db, permission_service) -> ClaudeService:
    return ClaudeService(db, permission_service)


@pytest.fixture
def mock_sdk():
    """Provide a mock claude_agent_sdk module in sys.modules."""
    mock_module = MagicMock()
    mock_module.ClaudeSDKClient = MagicMock
    mock_module.ClaudeAgentOptions = MagicMock
    mock_module.AssistantMessage = type("AssistantMessage", (), {})
    mock_module.ResultMessage = type("ResultMessage", (), {})
    mock_module.SystemMessage = type("SystemMessage", (), {})
    mock_module.UserMessage = type("UserMessage", (), {})
    mock_module.ClaudeSDKError = type("ClaudeSDKError", (Exception,), {})
    mock_module.CLINotFoundError = type("CLINotFoundError", (Exception,), {})
    mock_module.CLIConnectionError = type("CLIConnectionError", (Exception,), {})
    mock_module.ProcessError = type("ProcessError", (Exception,), {})
    mock_module.PermissionResultAllow = MagicMock
    mock_module.PermissionResultDeny = MagicMock

    original = sys.modules.get("claude_agent_sdk")
    sys.modules["claude_agent_sdk"] = mock_module
    yield mock_module
    if original is not None:
        sys.modules["claude_agent_sdk"] = original
    else:
        sys.modules.pop("claude_agent_sdk", None)


# ---------------------------------------------------------------------------
# Helper: async iterator for mocking SDK stream
# ---------------------------------------------------------------------------

class MockAsyncIterator:
    """Mock async iterator for SDK message stream."""
    def __init__(self, items: list[Any]) -> None:
        self._items = items
        self._index = 0

    def __aiter__(self) -> MockAsyncIterator:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


# ---------------------------------------------------------------------------
# Environment sanitization tests
# ---------------------------------------------------------------------------

class TestSanitizeEnv:

    def test_sanitize_env_value_removes_null_bytes(self) -> None:
        assert _sanitize_env_value("hello\x00world") == "helloworld"

    def test_sanitize_env_value_removes_control_chars(self) -> None:
        assert _sanitize_env_value("test\x01\x02\x03value") == "testvalue"

    def test_sanitize_env_value_keeps_normal_text(self) -> None:
        assert _sanitize_env_value("normal text") == "normal text"

    def test_sanitize_env_value_keeps_newlines_tabs(self) -> None:
        # \n (\x0a) and \r (\x0d) and \t (\x09) are NOT in the regex range
        assert _sanitize_env_value("line1\nline2\ttab\rreturn") == "line1\nline2\ttab\rreturn"

    def test_sanitize_env_filters_non_string_values(self) -> None:
        env = {"KEY1": "value", "KEY2": "ok", "KEY3": 123}  # type: ignore[dict-item]
        result = _sanitize_env(env)
        assert "KEY1" in result
        assert "KEY2" in result
        assert "KEY3" not in result


# ---------------------------------------------------------------------------
# Dispatch handler tests
# ---------------------------------------------------------------------------

class TestClaudeServiceDispatch:
    """Tests for _dispatch_message and its sub-handlers."""

    def test_dispatch_assistant_text(self, claude_service: ClaudeService) -> None:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello from Claude"
        message = MagicMock()
        message.type = "assistant"
        message.content = [text_block]

        collected: list[str] = []
        claude_service._dispatch_message(message, on_text=collected.append)
        assert collected == ["Hello from Claude"]

    def test_dispatch_assistant_tool_use(self, claude_service: ClaudeService) -> None:
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool-1"
        tool_block.name = "Read"
        tool_block.input = {"path": "a.py"}
        message = MagicMock()
        message.type = "assistant"
        message.content = [tool_block]

        collected: list[dict[str, Any]] = []
        claude_service._dispatch_message(message, on_tool_use=collected.append)
        assert len(collected) == 1
        assert collected[0]["name"] == "Read"
        assert collected[0]["id"] == "tool-1"

    def test_dispatch_user_tool_result(self, claude_service: ClaudeService) -> None:
        result_block = MagicMock()
        result_block.type = "tool_result"
        result_block.tool_use_id = "tool-1"
        result_block.content = "file contents here"
        result_block.is_error = False
        message = MagicMock()
        message.type = "user"
        message.content = [result_block]

        collected: list[dict[str, Any]] = []
        claude_service._dispatch_message(message, on_tool_result=collected.append)
        assert len(collected) == 1
        assert collected[0]["tool_use_id"] == "tool-1"
        assert collected[0]["content"] == "file contents here"
        assert collected[0]["is_error"] is False

    def test_dispatch_user_tool_result_list_content(self, claude_service: ClaudeService) -> None:
        """Tool result with content as list of text blocks."""
        text_part = MagicMock()
        text_part.type = "text"
        text_part.text = "part1"
        text_part2 = MagicMock()
        text_part2.type = "text"
        text_part2.text = "part2"
        result_block = MagicMock()
        result_block.type = "tool_result"
        result_block.tool_use_id = "tool-2"
        result_block.content = [
            {"type": "text", "text": "part1"},
            {"type": "text", "text": "part2"},
        ]
        result_block.is_error = False
        message = MagicMock()
        message.type = "user"
        message.content = [result_block]

        collected: list[dict[str, Any]] = []
        claude_service._dispatch_message(message, on_tool_result=collected.append)
        assert collected[0]["content"] == "part1\npart2"

    def test_dispatch_result_message(self, claude_service: ClaudeService) -> None:
        usage = MagicMock()
        usage.input_tokens = 100
        usage.output_tokens = 50
        usage.cache_read_input_tokens = 10
        usage.cache_creation_input_tokens = 5
        message = MagicMock()
        message.type = "result"
        message.session_id = "sdk-123"
        message.subtype = "success"
        message.is_error = False
        message.num_turns = 3
        message.duration_ms = 5000
        message.usage = usage
        message.total_cost_usd = 0.05

        collected: list[dict[str, Any]] = []
        claude_service._dispatch_message(message, on_result=collected.append)
        assert len(collected) == 1
        result = collected[0]
        assert result["session_id"] == "sdk-123"
        assert result["is_error"] is False
        assert result["usage"]["input_tokens"] == 100
        assert result["usage"]["cost_usd"] == 0.05

    def test_dispatch_system_init(self, claude_service: ClaudeService) -> None:
        message = MagicMock()
        message.type = "system"
        message.subtype = "init"
        message.session_id = "sdk-abc"
        message.model = "claude-sonnet-4-5"
        message.tools = ["Read", "Write"]
        message.data = {}

        collected: list[dict[str, Any]] = []
        claude_service._dispatch_message(message, on_status=collected.append)
        assert collected[0]["type"] == "system"
        assert collected[0]["subtype"] == "init"
        assert collected[0]["session_id"] == "sdk-abc"

    def test_dispatch_stream_event(self, claude_service: ClaudeService) -> None:
        delta = MagicMock()
        delta.type = "text_delta"
        delta.text = "streaming chunk"
        event = MagicMock()
        event.type = "content_block_delta"
        event.delta = delta
        message = MagicMock()
        message.type = "stream_event"
        message.event = event

        collected: list[str] = []
        claude_service._dispatch_message(message, on_text=collected.append)
        assert collected == ["streaming chunk"]

    def test_dispatch_tool_progress(self, claude_service: ClaudeService) -> None:
        message = MagicMock()
        message.type = "tool_progress"
        message.tool_use_id = "tool-5"
        message.tool_name = "Bash"
        message.elapsed_time_seconds = 2.5

        collected: list[dict[str, Any]] = []
        claude_service._dispatch_message(message, on_status=collected.append)
        assert collected[0]["type"] == "tool_progress"
        assert collected[0]["tool_name"] == "Bash"

    def test_dispatch_no_callbacks(self, claude_service: ClaudeService) -> None:
        """Dispatch with no callbacks should not raise."""
        message = MagicMock()
        message.type = "assistant"
        message.content = []
        claude_service._dispatch_message(message)

    def test_dispatch_unknown_type(self, claude_service: ClaudeService) -> None:
        """Unknown message types are silently ignored."""
        message = MagicMock()
        message.type = "unknown_future_type"
        claude_service._dispatch_message(message)


# ---------------------------------------------------------------------------
# send_message tests (require SDK mock)
# ---------------------------------------------------------------------------

class TestClaudeServiceSendMessage:

    @pytest.mark.asyncio
    async def test_send_message_streams_text(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        """send_message iterates over SDK responses and calls on_text."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        inner_msg = MagicMock()
        inner_msg.content = [text_block]
        sdk_message = MagicMock()
        sdk_message.type = "assistant"
        sdk_message.content = [text_block]

        mock_client = MagicMock(spec=["send_message", "__aenter__", "__aexit__"])
        mock_client.send_message = MagicMock(return_value=MockAsyncIterator([sdk_message]))

        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collected: list[str] = []

        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            await claude_service.send_message(
                "session-1", "Say hello",
                on_text=collected.append,
            )

        assert collected == ["Hello!"]
        assert claude_service.is_streaming is False

    @pytest.mark.asyncio
    async def test_send_message_cli_not_found(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        """CLINotFoundError calls on_error."""
        cli_err_cls = mock_sdk.CLINotFoundError

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=cli_err_cls("not found"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)

        errors: list[str] = []
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            await claude_service.send_message(
                "session-1", "hi",
                on_error=errors.append,
            )

        assert len(errors) == 1
        assert "cli" in errors[0].lower() or "not found" in errors[0].lower()

    @pytest.mark.asyncio
    async def test_send_message_generic_error(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        """Generic exceptions are caught and forwarded to on_error."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)

        errors: list[str] = []
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            await claude_service.send_message(
                "session-1", "hi",
                on_error=errors.append,
            )

        assert len(errors) == 1
        assert "boom" in errors[0]

    @pytest.mark.asyncio
    async def test_send_message_sdk_error(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        """ClaudeSDKError calls on_error."""
        sdk_err_cls = mock_sdk.ClaudeSDKError

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=sdk_err_cls("sdk broke"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)

        errors: list[str] = []
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            await claude_service.send_message(
                "session-1", "hi",
                on_error=errors.append,
            )

        assert len(errors) == 1
        assert "sdk" in errors[0].lower()

    @pytest.mark.asyncio
    async def test_abort_with_explicit_session(self, claude_service: ClaudeService) -> None:
        """abort() clears session state and calls client.abort() when present."""
        mock_client = AsyncMock()
        session_id = "session-1"
        claude_service._active_streams[session_id] = True
        claude_service._abort_events[session_id] = asyncio.Event()
        claude_service._clients[session_id] = mock_client

        await claude_service.abort(session_id)

        assert claude_service.is_streaming is False
        assert claude_service._abort_events[session_id].is_set()
        mock_client.abort.assert_awaited_once()
        assert session_id not in claude_service._clients

    @pytest.mark.asyncio
    async def test_send_message_aborted_mid_stream(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        """Abort during streaming stops iteration."""
        msg1 = MagicMock(type="assistant", content=[])

        async def abort_during_iter():
            yield msg1
            claude_service._abort_events["session-1"].set()
            yield msg1  # Should not process this

        mock_client = MagicMock(spec=["send_message", "__aenter__", "__aexit__"])
        mock_client.send_message = MagicMock(return_value=abort_during_iter())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)

        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            await claude_service.send_message("session-1", "hi")

        assert claude_service.is_streaming is False


# ---------------------------------------------------------------------------
# _build_options tests
# ---------------------------------------------------------------------------

class TestBuildOptions:

    def test_build_options_default(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        mock_sdk.ClaudeAgentOptions = MagicMock(return_value=MagicMock())
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            options = claude_service._build_options()
            mock_sdk.ClaudeAgentOptions.assert_called_once()

    def test_build_options_with_resume(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        mock_opts_instance = MagicMock()
        mock_sdk.ClaudeAgentOptions = MagicMock(return_value=mock_opts_instance)
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            claude_service._build_options(sdk_session_id="sdk-resume-123")
            assert mock_opts_instance.resume == "sdk-resume-123"

    def test_build_options_with_model(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        mock_opts_instance = MagicMock()
        mock_sdk.ClaudeAgentOptions = MagicMock(return_value=mock_opts_instance)
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            claude_service._build_options(model="claude-opus-4")
            assert mock_opts_instance.model == "claude-opus-4"

    def test_build_options_bypass_permissions(self, claude_service: ClaudeService, db: Any, mock_sdk: Any) -> None:
        db.set_setting("dangerously_skip_permissions", "true")
        mock_opts_instance = MagicMock()
        mock_sdk.ClaudeAgentOptions = MagicMock(return_value=mock_opts_instance)
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            claude_service._build_options()
            call_kwargs = mock_sdk.ClaudeAgentOptions.call_args
            assert call_kwargs.kwargs.get("permission_mode") == "bypassPermissions"

    def test_build_options_with_mcp_servers(self, claude_service: ClaudeService, mock_sdk: Any) -> None:
        mock_opts_instance = MagicMock()
        mock_sdk.ClaudeAgentOptions = MagicMock(return_value=mock_opts_instance)
        mcp = {"fs": {"command": "npx", "args": ["-y", "@anthropic/fs-mcp"]}}
        with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value=None):
            claude_service._build_options(mcp_servers=mcp)
            assert mock_opts_instance.mcp_servers == mcp

    def test_build_options_uses_sdk_safe_claude_binary(
        self, claude_service: ClaudeService, mock_sdk: Any
    ) -> None:
        mock_opts_instance = MagicMock()
        mock_sdk.ClaudeAgentOptions = MagicMock(return_value=mock_opts_instance)
        with patch(
            "misaka.services.chat.claude_service.find_claude_sdk_binary",
            return_value="C:/npm/claude.exe",
        ):
            options = claude_service._build_options()
            assert options.cli_path == "C:/npm/claude.exe"


# ---------------------------------------------------------------------------
# Permission callback tests
# ---------------------------------------------------------------------------

class TestPermissionCallback:

    @pytest.mark.asyncio
    async def test_permission_allow(
        self, claude_service: ClaudeService, permission_service: PermissionService, mock_sdk: Any
    ) -> None:
        """Permission callback returns allow when user allows."""
        requests: list[dict[str, Any]] = []

        def on_permission_request(req: dict[str, Any]) -> None:
            requests.append(req)
            permission_service.resolve(req["permission_id"], {"behavior": "allow"})

        callback = claude_service._make_permission_callback(on_permission_request)

        mock_sdk.PermissionResultAllow = MagicMock(return_value="allowed")
        mock_sdk.PermissionResultDeny = MagicMock(return_value="denied")

        result = await callback("Read", {"file_path": "test.py"})
        assert result == "allowed"
        assert len(requests) == 1

    @pytest.mark.asyncio
    async def test_permission_deny(
        self, claude_service: ClaudeService, permission_service: PermissionService, mock_sdk: Any
    ) -> None:
        """Permission callback returns deny when user denies."""
        def on_permission_request(req: dict[str, Any]) -> None:
            permission_service.resolve(req["permission_id"], {"behavior": "deny", "message": "Nope"})

        callback = claude_service._make_permission_callback(on_permission_request)

        mock_sdk.PermissionResultAllow = MagicMock(return_value="allowed")
        mock_sdk.PermissionResultDeny = MagicMock(return_value="denied")

        result = await callback("Bash", {"command": "rm -rf /"})
        assert result == "denied"
