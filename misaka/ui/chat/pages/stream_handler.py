"""Stream handler for Claude SDK responses.

Encapsulates all streaming logic: callback wiring, block accumulation,
serialization, finalization, and UI refresh during a streaming turn.
Extracted from ``ChatPage`` to keep that class focused on layout and
session orchestration.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from misaka.state import (
    PermissionRequest,
    StreamingTextBlock,
    StreamingToolUseBlock,
    TokenUsageInfo,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import ChatSession
    from misaka.state import AppState

logger = logging.getLogger(__name__)

# Tools that are auto-allowed in "acceptEdits" mode
_READ_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch", "LS"})
_EDIT_TOOLS = frozenset({"Edit"})


class StreamHandler:
    """Manages a single streaming turn between the user and Claude.

    Parameters
    ----------
    state:
        Shared application state.
    db:
        Database backend for persisting messages and session metadata.
    ui_refresh:
        Callable invoked whenever the UI needs to repaint streaming
        progress (message list + permission overlay).
    on_title_changed:
        Callable invoked after session title is auto-synced so the UI
        can refresh the chat list / chat view header.
    """

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend,
        ui_refresh: Callable[[], None],
        on_title_changed: Callable[[], None] | None = None,
    ) -> None:
        self._state = state
        self._db = db
        self._ui_refresh = ui_refresh
        self._on_title_changed = on_title_changed
        self._send_override: Any = None
        self._abort_override: Any = None
        self._always_allowed_tools: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def persist_user_message(self, text: str) -> None:
        """Save a user message to the DB, append to state, and start streaming."""
        if not self._state.current_session_id:
            return
        content_json = json.dumps([{"type": "text", "text": text}])
        msg = self._db.add_message(
            self._state.current_session_id, "user", content_json,
        )
        self._state.messages.append(msg)
        self.start_streaming()

    async def send_to_claude(self, prompt: str) -> None:
        """Stream a prompt to Claude and finalize the result."""
        session = self._state.current_session
        claude = self._state.get_service("claude_service")
        if not session or not claude:
            self._state.error_message = "Claude service unavailable."
            self.reset_stream_state()
            self._ui_refresh()
            return

        result_usage: dict[str, Any] | None = None
        result_sdk_session_id: str | None = None
        stream_error: str | None = None

        def on_text(text: str) -> None:
            self._append_stream_text(text)
            self._ui_refresh()

        def on_tool_use(payload: dict) -> None:
            self._append_tool_use(payload)
            self._ui_refresh()

        def on_tool_result(payload: dict) -> None:
            self._append_tool_result(payload)
            self._ui_refresh()

        def on_result(payload: dict) -> None:
            nonlocal result_usage, result_sdk_session_id
            result_usage = payload.get("usage")
            result_sdk_session_id = payload.get("session_id") or None

        def on_status(payload: dict) -> None:
            nonlocal result_sdk_session_id
            if payload.get("subtype") == "init":
                result_sdk_session_id = (
                    payload.get("session_id") or result_sdk_session_id
                )

        def on_error(message: str) -> None:
            nonlocal stream_error
            stream_error = message

        def on_permission_request(payload: dict) -> None:
            self._state.pending_permission = PermissionRequest(
                id=payload.get("permission_id", ""),
                tool_name=payload.get("tool_name", ""),
                tool_input=payload.get("tool_input", {}) or {},
                suggestions=payload.get("suggestions"),
                decision_reason=payload.get("decision_reason"),
            )
            self._ui_refresh()

        await claude.send_message(
            session_id=session.id,
            prompt=prompt,
            model=session.model or None,
            system_prompt=session.system_prompt or None,
            working_directory=session.working_directory or None,
            sdk_session_id=session.sdk_session_id or None,
            mcp_servers=self._state.mcp_servers_sdk or None,
            permission_mode=self._get_global_permission_mode(),
            should_auto_allow=self._make_should_auto_allow(self._get_global_permission_mode()),
            on_text=on_text,
            on_tool_use=on_tool_use,
            on_tool_result=on_tool_result,
            on_status=on_status,
            on_result=on_result,
            on_error=on_error,
            on_permission_request=on_permission_request,
        )
        self._finalize_stream(
            session, result_usage, result_sdk_session_id, stream_error,
        )

    async def abort_claude(self) -> None:
        """Abort the current streaming operation."""
        claude = self._state.get_service("claude_service")
        if claude:
            await claude.abort()
        self.reset_stream_state()
        self._ui_refresh()

    def set_callbacks(
        self,
        send_callback: Any = None,
        abort_callback: Any = None,
    ) -> None:
        """Register optional override callbacks for send/abort."""
        self._send_override = send_callback
        self._abort_override = abort_callback

    def get_send_coroutine(self, prompt: str) -> tuple[Any, ...]:
        """Return ``(coro, *args)`` for dispatching a send task."""
        if self._send_override:
            return (self._send_override, prompt)
        return (self.send_to_claude, prompt)

    def get_abort_coroutine(self) -> tuple[Any, ...]:
        """Return ``(coro, *args)`` for dispatching an abort task."""
        if self._abort_override:
            return (self._abort_override,)
        return (self.abort_claude,)

    def resolve_permission(self, allow: bool, always: bool = False) -> None:
        """Resolve a pending permission request from the SDK."""
        req = self._state.pending_permission
        if allow and always and req:
            self._always_allowed_tools.add(req.tool_name)
        self._state.pending_permission = None
        perm_svc = self._state.get_service("permission_service")
        if req and perm_svc:
            decision = {"behavior": "allow"} if allow else {
                "behavior": "deny",
                "message": "User denied permission",
            }
            perm_svc.resolve(req.id, decision)
        self._ui_refresh()

    # ------------------------------------------------------------------
    # Stream state helpers
    # ------------------------------------------------------------------

    def start_streaming(self) -> None:
        """Mark the beginning of a new streaming turn."""
        self._state.is_streaming = True
        self._state.streaming_blocks = []
        self._state.streaming_session_id = self._state.current_session_id
        self._state.error_message = None

    def reset_stream_state(self) -> None:
        """Clear all streaming-related state."""
        self._state.clear_streaming()
        self._state.pending_permission = None

    # ------------------------------------------------------------------
    # Block accumulation
    # ------------------------------------------------------------------

    def _append_stream_text(self, text: str) -> None:
        if not self._state.streaming_blocks:
            self._state.streaming_blocks.append(StreamingTextBlock())
        last = self._state.streaming_blocks[-1]
        if isinstance(last, StreamingTextBlock):
            last.text += text
            return
        self._state.streaming_blocks.append(StreamingTextBlock(text=text))

    def _append_tool_use(self, payload: dict) -> None:
        self._state.streaming_blocks.append(
            StreamingToolUseBlock(
                id=payload.get("id", ""),
                name=payload.get("name", ""),
                input=payload.get("input", {}) or {},
            )
        )

    def _append_tool_result(self, payload: dict) -> None:
        tool_id = payload.get("tool_use_id", "")
        for block in reversed(self._state.streaming_blocks):
            if isinstance(block, StreamingToolUseBlock) and block.id == tool_id:
                block.output = payload.get("content", "")
                block.is_error = bool(payload.get("is_error"))
                return

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize_stream_blocks(self) -> tuple[str, str]:
        """Serialize accumulated blocks to a JSON or plain-text string.

        Returns ``(content, format)`` where *format* is ``"json"``
        when tool-use blocks are present, otherwise ``"text"``.
        """
        blocks: list[dict] = []
        plain_parts: list[str] = []
        has_tool = False
        for block in self._state.streaming_blocks:
            if isinstance(block, StreamingTextBlock) and block.text:
                blocks.append({"type": "text", "text": block.text})
                plain_parts.append(block.text)
            elif isinstance(block, StreamingToolUseBlock):
                has_tool = True
                blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
                if block.output is not None:
                    blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": block.output,
                        "is_error": block.is_error,
                    })
        if has_tool:
            return json.dumps(blocks, ensure_ascii=False), "json"
        return "".join(plain_parts).strip(), "text"

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def _finalize_stream(
        self,
        session: ChatSession,
        result_usage: dict[str, Any] | None,
        result_sdk_session_id: str | None,
        stream_error: str | None,
    ) -> None:
        active_sdk_id = result_sdk_session_id or session.sdk_session_id or None
        self._persist_assistant_message(session, result_usage)
        self._update_sdk_session(session, result_sdk_session_id)
        self._maybe_sync_session_title(session, active_sdk_id)
        if stream_error:
            self._state.error_message = stream_error
        self.reset_stream_state()
        self._ui_refresh()

    def _persist_assistant_message(
        self,
        session: ChatSession,
        result_usage: dict[str, Any] | None,
    ) -> None:
        content, _ = self._serialize_stream_blocks()
        if not content:
            return
        usage_json = json.dumps(result_usage) if result_usage else None
        msg = self._db.add_message(
            session_id=session.id,
            role="assistant",
            content=content,
            token_usage=usage_json,
        )
        self._state.messages.append(msg)
        if result_usage:
            self._state.last_token_usage = TokenUsageInfo(**result_usage)

    def _update_sdk_session(
        self,
        session: ChatSession,
        result_sdk_session_id: str | None,
    ) -> None:
        if not result_sdk_session_id:
            return
        session.sdk_session_id = result_sdk_session_id
        self._state.sdk_session_id = result_sdk_session_id
        self._db.update_sdk_session_id(session.id, result_sdk_session_id)

    # ------------------------------------------------------------------
    # Session title sync
    # ------------------------------------------------------------------

    def _maybe_sync_session_title(
        self,
        session: ChatSession,
        sdk_session_id: str | None,
    ) -> None:
        """Auto-sync session title after first successful round."""
        if not self._is_default_session_title(session.title):
            return

        new_title = self._title_from_claude_session(sdk_session_id)
        if not new_title:
            new_title = self._title_from_first_user_message()
        if not new_title:
            return

        new_title = new_title.strip()
        if not new_title or new_title == session.title:
            return

        session.title = new_title
        self._db.update_session_title(session.id, new_title)
        if self._on_title_changed:
            self._on_title_changed()

    @staticmethod
    def _is_default_session_title(title: str) -> bool:
        normalized = (title or "").strip().lower()
        return normalized in {"", "new chat"}

    def _title_from_claude_session(self, sdk_session_id: str | None) -> str | None:
        if not sdk_session_id:
            return None
        import_svc = self._state.get_service("session_import_service")
        if not import_svc:
            return None
        try:
            return import_svc.get_session_title(sdk_session_id)
        except Exception:
            return None

    def _title_from_first_user_message(self) -> str | None:
        for msg in self._state.messages:
            if msg.role != "user":
                continue
            for block in msg.parse_content():
                if block.type != "text" or not block.text:
                    continue
                first_line = block.text.strip().splitlines()[0].strip()
                if not first_line:
                    continue
                words = first_line.split()
                if len(words) <= 12 and len(first_line) <= 60:
                    return first_line
                short = " ".join(words[:12]).strip()
                return (short + "...") if short else None
        return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _get_global_permission_mode(self) -> str:
        """Read the global permission mode from settings."""
        settings_svc = self._state.get_service("settings_service")
        if settings_svc and hasattr(settings_svc, "get_permission_mode"):
            return settings_svc.get_permission_mode()
        return "acceptEdits"

    def _make_should_auto_allow(self, permission_mode: str) -> Callable[[str], bool] | None:
        """Build a callable that determines whether a tool call should be auto-approved.

        Returns None when bypassPermissions is active (SDK handles everything).
        """
        if permission_mode == "bypassPermissions":
            return None

        always_allowed = self._always_allowed_tools

        def should_auto_allow(tool_name: str) -> bool:
            if tool_name in always_allowed:
                return True
            if permission_mode == "acceptEdits":
                return tool_name in (_READ_TOOLS | _EDIT_TOOLS)
            return False  # "default": ask for everything

        return should_auto_allow
