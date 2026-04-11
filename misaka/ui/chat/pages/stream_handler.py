"""Stream handler for Claude SDK responses.

Encapsulates all streaming logic: callback wiring, block accumulation,
serialization, finalization, and UI refresh during a streaming turn.
Extracted from ``ChatPage`` to keep that class focused on layout and
session orchestration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from misaka.errors import ErrorClassifier
from misaka.state import (
    PermissionRequest,
    StreamingBlock,
    StreamingTextBlock,
    StreamingThinkingBlock,
    StreamingToolUseBlock,
    TokenUsageInfo,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import ChatSession, Message
    from misaka.state import AppState

logger = logging.getLogger(__name__)

# Tools that are auto-allowed in "acceptEdits" mode
_READ_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch", "LS"})
_EDIT_TOOLS = frozenset({"Edit"})


@dataclass
class _StreamContext:
    """Per-invocation mutable context captured by send_to_claude() closures.

    Mutating ``is_foreground`` from outside redirects all future callback
    writes between the foreground UI and the background accumulator.
    """
    session_id: str
    generation: int
    is_foreground: bool = True
    cancelled: bool = False
    blocks: list[StreamingBlock] = field(default_factory=list)


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
        on_background_status_change: Callable[[], None] | None = None,
    ) -> None:
        self._state = state
        self._db = db
        self._ui_refresh = ui_refresh
        self._on_title_changed = on_title_changed
        self._on_background_status_change = on_background_status_change
        self._send_override: Any = None
        self._abort_override: Any = None
        self._always_allowed_tools: set[str] = set()
        # Per-invocation stream context (foreground)
        self._active_ctx: _StreamContext | None = None
        # Detached contexts still running in background
        self._detached_contexts: dict[str, _StreamContext] = {}
        # Throttling: limit UI refreshes to ~30fps during streaming
        self._last_refresh_time: float = 0.0
        self._refresh_pending: bool = False
        self._refresh_timer: asyncio.TimerHandle | None = None
        self._stream_generation: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _throttled_ui_refresh(self) -> None:
        """Rate-limit UI refreshes to ~30fps (33ms) during streaming.

        If called within 33ms of the last refresh, schedules a deferred
        refresh instead of refreshing immediately.
        """
        now = time.monotonic()
        elapsed = now - self._last_refresh_time
        if elapsed >= 0.033:
            self._last_refresh_time = now
            self._refresh_pending = False
            if self._refresh_timer is not None:
                self._refresh_timer.cancel()
                self._refresh_timer = None
            self._ui_refresh()
        elif not self._refresh_pending:
            self._refresh_pending = True
            delay = 0.033 - elapsed
            try:
                loop = asyncio.get_event_loop()
                self._refresh_timer = loop.call_later(
                    delay, self._flush_pending_refresh,
                )
            except RuntimeError:
                # No event loop — fall back to immediate refresh
                self._ui_refresh()

    def _flush_pending_refresh(self) -> None:
        """Execute a deferred refresh scheduled by _throttled_ui_refresh."""
        self._refresh_pending = False
        self._refresh_timer = None
        self._last_refresh_time = time.monotonic()
        self._ui_refresh()

    def _is_current_foreground_ctx(self, ctx: _StreamContext) -> bool:
        """Return whether the context still owns the current foreground stream."""
        return (
            ctx.is_foreground
            and ctx.generation == self._stream_generation
            and self._state.is_streaming
            and self._state.streaming_session_id == ctx.session_id
        )

    def persist_user_message(
        self,
        text: str,
        images: list | None = None,
    ) -> Message | None:
        """Save a user message to the DB, append to state, and start streaming.

        Args:
            text: The text content of the message.
            images: Optional list of PendingImage objects.

        Returns the new Message for minimal UI refresh, or None if no session.
        """
        if not self._state.current_session_id:
            return None

        # Build content blocks
        content_blocks: list[dict] = []

        # Add image blocks first (if any)
        if images:
            for img in images:
                content_blocks.append({
                    "type": "image",
                    "source_type": "file",
                    "file_path": img.temp_path,
                    "media_type": img.mime_type,
                    "alt_text": img.original_name,
                })

        # Add text block
        if text:
            content_blocks.append({"type": "text", "text": text})

        content_json = json.dumps(content_blocks)
        msg = self._db.add_message(
            self._state.current_session_id, "user", content_json,
        )
        self._state.messages.append(msg)
        self.start_streaming()
        return msg

    async def send_to_claude(
        self,
        prompt: str,
        images: list | None = None,
    ) -> None:
        """Stream a prompt to Claude and finalize the result.

        Args:
            prompt: The text prompt to send.
            images: Optional list of PendingImage objects to send as multimodal content.
        """
        session = self._state.current_session
        claude = self._state.get_service("claude_service")
        if not session or not claude:
            from misaka.i18n import t
            classified = ErrorClassifier.classify_error_string("Claude service unavailable")
            self._state.error_message = ErrorClassifier.format_user_message(classified, translate=t)
            self.reset_stream_state()
            self._ui_refresh()
            return

        ctx = _StreamContext(
            session_id=session.id,
            generation=self._stream_generation,
        )
        self._active_ctx = ctx

        result_usage: dict[str, Any] | None = None
        result_sdk_session_id: str | None = None
        stream_error: str | None = None

        def _append_thinking_to_ctx(text: str) -> None:
            """Append thinking text to the context's block list."""
            if ctx.blocks and isinstance(ctx.blocks[-1], StreamingThinkingBlock):
                ctx.blocks[-1].thinking += text
                return
            ctx.blocks.append(StreamingThinkingBlock(thinking=text))

        def _append_text_to_ctx(text: str) -> None:
            """Append text to the context's block list."""
            if not ctx.blocks:
                ctx.blocks.append(StreamingTextBlock())
            last = ctx.blocks[-1]
            if isinstance(last, StreamingTextBlock):
                last.text += text
                return
            ctx.blocks.append(StreamingTextBlock(text=text))

        def _append_tool_use_to_ctx(payload: dict) -> None:
            ctx.blocks.append(
                StreamingToolUseBlock(
                    id=payload.get("id", ""),
                    name=payload.get("name", ""),
                    input=payload.get("input", {}) or {},
                )
            )

        def _append_tool_result_to_ctx(payload: dict) -> None:
            tool_id = payload.get("tool_use_id", "")
            for block in reversed(ctx.blocks):
                if isinstance(block, StreamingToolUseBlock) and block.id == tool_id:
                    block.output = payload.get("content", "")
                    block.is_error = bool(payload.get("is_error"))
                    return

        def on_text(text: str) -> None:
            if self._is_current_foreground_ctx(ctx):
                self._append_stream_text(text)
                self._throttled_ui_refresh()
            _append_text_to_ctx(text)

        def on_thinking(text: str) -> None:
            if self._is_current_foreground_ctx(ctx):
                self._append_stream_thinking(text)
                self._throttled_ui_refresh()
            _append_thinking_to_ctx(text)

        def on_tool_use(payload: dict) -> None:
            if self._is_current_foreground_ctx(ctx):
                self._append_tool_use(payload)
                self._ui_refresh()
            _append_tool_use_to_ctx(payload)

        def on_tool_result(payload: dict) -> None:
            if self._is_current_foreground_ctx(ctx):
                self._append_tool_result(payload)
                self._ui_refresh()
            _append_tool_result_to_ctx(payload)

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
            if not self._is_current_foreground_ctx(ctx):
                # Auto-deny permissions when running in background
                perm_svc = self._state.get_service("permission_service")
                perm_id = payload.get("permission_id", "")
                if perm_svc:
                    perm_svc.resolve(perm_id, {
                        "behavior": "deny",
                        "message": "Auto-denied: session is running in background",
                    })
                return
            self._state.pending_permission = PermissionRequest(
                id=payload.get("permission_id", ""),
                tool_name=payload.get("tool_name", ""),
                tool_input=payload.get("tool_input", {}) or {},
                suggestions=payload.get("suggestions"),
                decision_reason=payload.get("decision_reason"),
            )
            self._ui_refresh()

        # Build multimodal content if images are present
        if images:
            content_blocks: list[dict] = []
            # Add images first - encode as base64
            image_service = self._state.get_service("image_service")
            for img in images:
                base64_data = None
                if image_service:
                    base64_data = image_service.get_image_base64(img.temp_path)
                if base64_data:
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.mime_type,
                            "data": base64_data,
                        },
                    })
            # Add text block
            if prompt:
                content_blocks.append({"type": "text", "text": prompt})
            message_content: str | list[dict] = content_blocks
        else:
            message_content = prompt

        await claude.send_message(
            session_id=session.id,
            prompt=message_content,
            model=session.model or None,
            system_prompt=session.system_prompt or None,
            working_directory=session.working_directory or None,
            sdk_session_id=session.sdk_session_id or None,
            mcp_servers=self._state.mcp_servers_sdk or None,
            session_mode=session.mode or "agent",
            permission_mode=self._get_global_permission_mode(),
            should_auto_allow=self._make_should_auto_allow(
                self._get_global_permission_mode(),
                session.mode or "agent",
            ),
            on_text=on_text,
            on_thinking=on_thinking,
            on_tool_use=on_tool_use,
            on_tool_result=on_tool_result,
            on_status=on_status,
            on_result=on_result,
            on_error=on_error,
            on_permission_request=on_permission_request,
        )

        # Clean up active context reference
        if self._active_ctx is ctx:
            self._active_ctx = None

        if self._is_current_foreground_ctx(ctx):
            self._finalize_stream(
                session, result_usage, result_sdk_session_id, stream_error,
            )
        elif not ctx.is_foreground and not ctx.cancelled:
            # Stream finished in background — finalize without touching foreground UI
            self._detached_contexts.pop(ctx.session_id, None)
            self._finalize_background(
                ctx, session, result_usage, result_sdk_session_id, stream_error,
            )
        else:
            self._detached_contexts.pop(ctx.session_id, None)

    async def abort_claude(self) -> None:
        await self.abort_claude_with_options()

    async def abort_claude_with_options(
        self,
        *,
        persist_interrupted: bool = True,
        refresh_ui: bool = True,
    ) -> None:
        """Abort the current streaming operation with optional persistence."""
        claude = self._state.get_service("claude_service")
        sid = self._state.streaming_session_id
        generation = self._stream_generation
        if claude and sid:
            await claude.abort(sid)
        if (
            sid != self._state.streaming_session_id
            or generation != self._stream_generation
        ):
            return
        if persist_interrupted:
            self._persist_interrupted_message()
        self.reset_stream_state()
        if refresh_ui:
            self._ui_refresh()

    def set_callbacks(
        self,
        send_callback: Any = None,
        abort_callback: Any = None,
    ) -> None:
        """Register optional override callbacks for send/abort."""
        self._send_override = send_callback
        self._abort_override = abort_callback

    def get_send_coroutine(
        self,
        prompt: str,
        images: list | None = None,
    ) -> tuple[Any, ...]:
        """Return ``(coro, *args)`` for dispatching a send task."""
        if self._send_override:
            return (self._send_override, prompt, images)
        return (self.send_to_claude, prompt, images)

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

    def detach_to_background(self) -> None:
        """Detach the current foreground stream to run in the background.

        Called by ChatPage when the user switches away from a streaming session.
        """
        ctx = self._active_ctx
        if not ctx or not ctx.is_foreground:
            return

        # Flip to background mode — future callbacks skip UI writes
        ctx.is_foreground = False

        # Register in background streams tracking
        bg_info = self._state.mark_background_streaming(ctx.session_id)
        # Share blocks by reference so _finalize_background can read them
        bg_info.blocks = ctx.blocks

        # Store reference for possible reattach
        self._detached_contexts[ctx.session_id] = ctx

        # Auto-deny any pending permission (can't show UI in background)
        if self._state.pending_permission:
            perm_svc = self._state.get_service("permission_service")
            req = self._state.pending_permission
            if perm_svc and req:
                perm_svc.resolve(req.id, {
                    "behavior": "deny",
                    "message": "Auto-denied: session moved to background",
                })
            self._state.pending_permission = None

        # Clear foreground streaming state
        self._state.clear_streaming()
        self._active_ctx = None

        if self._on_background_status_change:
            self._on_background_status_change()

    def reattach_to_foreground(self, session_id: str) -> None:
        """Re-attach a background stream to the foreground.

        Called when the user switches back to a session that is still
        streaming in the background.
        """
        ctx = self._detached_contexts.get(session_id)
        bg_info = self._state.background_streams.get(session_id)

        if not ctx or not bg_info:
            return

        # Restore foreground streaming state from accumulated blocks
        self._state.streaming_blocks = list(ctx.blocks)
        self._state.is_streaming = True
        self._state.streaming_session_id = session_id

        # Flip context back to foreground
        ctx.is_foreground = True
        self._active_ctx = ctx

        # Remove from detached/background tracking
        self._detached_contexts.pop(session_id, None)
        self._state.background_streams.pop(session_id, None)

        if self._on_background_status_change:
            self._on_background_status_change()

    def cancel_background_stream(self, session_id: str) -> None:
        """Mark a detached background stream as cancelled before aborting it."""
        ctx = self._detached_contexts.get(session_id)
        if ctx is not None:
            ctx.cancelled = True

    # ------------------------------------------------------------------
    # Stream state helpers
    # ------------------------------------------------------------------

    def start_streaming(self) -> None:
        """Mark the beginning of a new streaming turn."""
        self._stream_generation += 1
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

    def _append_stream_thinking(self, text: str) -> None:
        blocks = self._state.streaming_blocks
        if blocks and isinstance(blocks[-1], StreamingThinkingBlock):
            blocks[-1].thinking += text
            return
        blocks.append(StreamingThinkingBlock(thinking=text))

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
        when tool-use or thinking blocks are present, otherwise ``"text"``.
        """
        return self._serialize_blocks(self._state.streaming_blocks)

    @staticmethod
    def _serialize_blocks(block_list: list[StreamingBlock]) -> tuple[str, str]:
        """Serialize an arbitrary block list to (content, format)."""
        blocks: list[dict] = []
        plain_parts: list[str] = []
        has_structured = False
        for block in block_list:
            if isinstance(block, StreamingThinkingBlock) and block.thinking:
                has_structured = True
                blocks.append({"type": "thinking", "thinking": block.thinking})
            elif isinstance(block, StreamingTextBlock) and block.text:
                blocks.append({"type": "text", "text": block.text})
                plain_parts.append(block.text)
            elif isinstance(block, StreamingToolUseBlock):
                has_structured = True
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
        if has_structured:
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

    def _finalize_background(
        self,
        ctx: _StreamContext,
        session: ChatSession,
        result_usage: dict[str, Any] | None,
        result_sdk_session_id: str | None,
        stream_error: str | None,
    ) -> None:
        """Finalize a stream that completed while in the background."""
        active_sdk_id = result_sdk_session_id or session.sdk_session_id or None
        # Persist assistant message from context blocks
        self._persist_assistant_message_from_blocks(
            ctx.blocks, session, result_usage,
        )
        self._update_sdk_session(session, result_sdk_session_id)
        self._maybe_sync_session_title(session, active_sdk_id)

        # Update background info
        bg_info = self._state.background_streams.get(ctx.session_id)
        if bg_info:
            bg_info.result_usage = result_usage
            bg_info.result_sdk_session_id = result_sdk_session_id
            bg_info.stream_error = stream_error

        # Mark as completed (dot changes from yellow to green)
        self._state.mark_background_completed(ctx.session_id)

        if self._on_background_status_change:
            self._on_background_status_change()

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

    def _persist_interrupted_message(self) -> None:
        """Persist partial streaming content with interrupted marker when user aborts."""
        session = self._state.current_session
        if not session or session.id != self._state.streaming_session_id:
            return
        content, fmt = self._serialize_stream_blocks()
        blocks = self._content_to_blocks_with_interrupted(content, fmt)
        if not blocks:
            return
        content_json = json.dumps(blocks, ensure_ascii=False)
        msg = self._db.add_message(
            session_id=session.id,
            role="assistant",
            content=content_json,
            token_usage=None,
        )
        self._state.messages.append(msg)

    @staticmethod
    def _content_to_blocks_with_interrupted(content: str, fmt: str) -> list[dict]:
        """Prepend interrupted marker to content blocks."""
        interrupted_block = {"type": "interrupted"}
        if fmt == "json":
            try:
                blocks = json.loads(content)
                if isinstance(blocks, list):
                    return [interrupted_block] + blocks
            except (json.JSONDecodeError, TypeError):
                pass
        return [interrupted_block, {"type": "text", "text": content or ""}]

    def _persist_assistant_message_from_blocks(
        self,
        blocks: list[StreamingBlock],
        session: ChatSession,
        result_usage: dict[str, Any] | None,
    ) -> None:
        """Persist assistant message from an arbitrary block list (background)."""
        content, _ = self._serialize_blocks(blocks)
        if not content:
            return
        usage_json = json.dumps(result_usage) if result_usage else None
        self._db.add_message(
            session_id=session.id,
            role="assistant",
            content=content,
            token_usage=usage_json,
        )

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
        return "default"

    def _make_should_auto_allow(
        self,
        permission_mode: str,
        session_mode: str = 'agent',
    ) -> Callable[[str], bool] | None:
        """Build a callable that determines whether a tool call should be auto-approved.

        Returns None when bypassPermissions is active (SDK handles everything).
        For "ask" mode, only read tools are auto-allowed.
        """
        if permission_mode == "bypassPermissions":
            return None

        always_allowed = self._always_allowed_tools

        def should_auto_allow(tool_name: str) -> bool:
            if tool_name in always_allowed:
                return True
            # In "ask" mode, only allow read tools
            if session_mode == "ask":
                return tool_name in _READ_TOOLS
            if permission_mode == "acceptEdits":
                return tool_name in (_READ_TOOLS | _EDIT_TOOLS)
            return False  # "default": ask for everything

        return should_auto_allow
