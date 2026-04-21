"""
Global state manager for Misaka.

Provides a centralized, reactive state object that drives all UI updates.
Components read from ``AppState``; services mutate it and call ``update()``
to trigger a Flet page refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import flet as ft

from misaka.db.models import ChatSession, Message, TaskItem

# ---------------------------------------------------------------------------
# Content block types used during streaming
# ---------------------------------------------------------------------------

@dataclass
class StreamingTextBlock:
    """Accumulated text content from a streaming response."""
    text: str = ""


@dataclass
class StreamingThinkingBlock:
    """Accumulated thinking/reasoning content from extended thinking."""
    thinking: str = ""


@dataclass
class StreamingToolUseBlock:
    """A tool invocation observed during streaming."""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    output: str | None = None
    is_error: bool = False


@dataclass
class PermissionRequest:
    """A pending permission request from the Claude SDK."""
    id: str
    tool_name: str
    tool_input: dict[str, Any]
    suggestions: list[dict[str, Any]] | None = None
    decision_reason: str | None = None


StreamingBlock = StreamingTextBlock | StreamingThinkingBlock | StreamingToolUseBlock


# ---------------------------------------------------------------------------
# Background stream tracking
# ---------------------------------------------------------------------------

class BackgroundStreamStatus(Enum):
    """Status of a background (detached) streaming session."""
    STREAMING = "streaming"
    COMPLETED_UNREAD = "completed"


@dataclass
class BackgroundStreamInfo:
    """Tracking info for a session streaming in the background."""
    status: BackgroundStreamStatus
    blocks: list[StreamingBlock] = field(default_factory=list)
    result_usage: dict[str, Any] | None = None
    result_sdk_session_id: str | None = None
    stream_error: str | None = None


# ---------------------------------------------------------------------------
# Token usage tracking
# ---------------------------------------------------------------------------

@dataclass
class TokenUsageInfo:
    """Token usage statistics for a single response."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float | None = None


# ---------------------------------------------------------------------------
# AppState
# ---------------------------------------------------------------------------

class AppState:
    """Centralized application state.

    All UI components hold a reference to a single ``AppState`` instance
    and read from its attributes.  Service methods mutate the state and
    call :meth:`update` to trigger a page-wide refresh.
    """

    def __init__(self, page: ft.Page) -> None:
        self.page = page

        # --- Service container (set by main.py after construction) ---
        self.services: Any = None  # ServiceContainer from main.py
        self.mcp_servers_sdk: dict[str, Any] = {}

        # --- Session state ---
        self._sessions: list[ChatSession] = []
        self._session_map: dict[str, ChatSession] = {}
        self.current_session_id: str | None = None

        # --- Message state ---
        self.messages: list[Message] = []
        self.has_more_messages: bool = False

        # --- Streaming state ---
        self.is_streaming: bool = False
        self.streaming_blocks: list[StreamingBlock] = []
        self.streaming_session_id: str | None = None

        # --- Background streams (detached sessions still running) ---
        self.background_streams: dict[str, BackgroundStreamInfo] = {}

        # --- Permission state ---
        self.pending_permission: PermissionRequest | None = None
        self._permission_future: Any = None  # asyncio.Future for permission dialog

        # --- Task state ---
        self.tasks: list[TaskItem] = []

        # --- Panel visibility ---
        self.left_panel_open: bool = True
        self.right_panel_open: bool = True

        # --- Navigation ---
        # "dashboard" | "chat" | "settings" | "plugins" | "extensions"
        self.current_page: str = "chat"

        # --- Theme ---
        self.theme_mode: str = "system"  # "system" | "light" | "dark"
        self.accent_color: str = "#6366f1"

        # --- File tree state ---
        self.file_tree_root: str | None = None
        self.file_tree_nodes: list[dict[str, Any]] = []
        self.file_tree_expanded_paths: set[str] = set()
        self.file_tree_loading_paths: set[str] = set()

        # --- Connection / status ---
        self.sdk_session_id: str | None = None
        self.last_token_usage: TokenUsageInfo | None = None
        self.error_message: str | None = None

        # --- Environment check state ---
        self.env_check_result: Any = None  # EnvironmentCheckResult
        self.env_check_loading: bool = False
        self.show_env_check_dialog: bool = False

        # --- UI loading states ---
        self.file_tree_loading: bool = False

        # --- Update check state ---
        self.update_check_result: Any = None  # UpdateCheckResult
        self.update_dismissed: bool = False
        self.update_in_progress: bool = False

        # --- i18n state ---
        self.locale: str = "zh-CN"

        # --- Model selection ---
        self.selected_model: str = "default"

        # --- Chat list grouping ---
        self.chat_group_mode: str = "date"  # "date" | "project"

        # --- Notification state ---
        self.notification_panel_open: bool = False

    # ----- Helpers -----

    def get_service(self, name: str) -> Any:
        """Safely retrieve a service by attribute name.

        Returns None if the service container is not yet initialised
        or the requested service does not exist.
        """
        services = getattr(self, "services", None)
        if services is None:
            return None
        return getattr(services, name, None)

    @property
    def current_session(self) -> ChatSession | None:
        """Return the currently selected session, if any."""
        if not self.current_session_id:
            return None
        return self._session_map.get(self.current_session_id)

    @property
    def sessions(self) -> list[ChatSession]:
        return self._sessions

    @sessions.setter
    def sessions(self, value: list[ChatSession]) -> None:
        self._sessions = value
        self._session_map = {s.id: s for s in value}

    def update(self) -> None:
        """Trigger a Flet page refresh.

        Call this after mutating state so that all components re-render
        with the latest data.
        """
        self.page.update()

    def clear_streaming(self) -> None:
        """Reset streaming-related state after a response completes."""
        self.is_streaming = False
        self.streaming_blocks = []
        self.streaming_session_id = None
        self.pending_permission = None

    # ----- Background stream helpers -----

    def mark_background_streaming(self, session_id: str) -> BackgroundStreamInfo:
        """Register a session as streaming in the background."""
        info = BackgroundStreamInfo(status=BackgroundStreamStatus.STREAMING)
        self.background_streams[session_id] = info
        return info

    def mark_background_completed(self, session_id: str) -> None:
        """Mark a background session as completed but not yet viewed."""
        info = self.background_streams.get(session_id)
        if info:
            info.status = BackgroundStreamStatus.COMPLETED_UNREAD

    def mark_background_viewed(self, session_id: str) -> None:
        """Remove a background session entry (user has viewed it)."""
        self.background_streams.pop(session_id, None)

    def get_background_status(self, session_id: str) -> BackgroundStreamStatus | None:
        """Return the background status for a session, or None if not backgrounded."""
        info = self.background_streams.get(session_id)
        return info.status if info else None

    def clear_error(self) -> None:
        """Dismiss the current error message."""
        self.error_message = None
