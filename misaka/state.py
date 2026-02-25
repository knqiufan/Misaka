"""
Global state manager for Misaka.

Provides a centralized, reactive state object that drives all UI updates.
Components read from ``AppState``; services mutate it and call ``update()``
to trigger a Flet page refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


StreamingBlock = StreamingTextBlock | StreamingToolUseBlock


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
        self.sessions: list[ChatSession] = []
        self.current_session_id: str | None = None

        # --- Message state ---
        self.messages: list[Message] = []
        self.has_more_messages: bool = False

        # --- Streaming state ---
        self.is_streaming: bool = False
        self.streaming_blocks: list[StreamingBlock] = []
        self.streaming_session_id: str | None = None

        # --- Permission state ---
        self.pending_permission: PermissionRequest | None = None
        self._permission_future: Any = None  # asyncio.Future for permission dialog

        # --- Task state ---
        self.tasks: list[TaskItem] = []

        # --- Panel visibility ---
        self.left_panel_open: bool = True
        self.right_panel_open: bool = True
        self.right_panel_tab: str = "files"  # "files" | "tasks"

        # --- Navigation ---
        self.current_page: str = "chat"  # "chat" | "settings" | "plugins" | "extensions"

        # --- Theme ---
        self.theme_mode: str = "system"  # "system" | "light" | "dark"

        # --- File tree state ---
        self.file_tree_root: str | None = None
        self.file_tree_nodes: list[dict[str, Any]] = []

        # --- Connection / status ---
        self.sdk_session_id: str | None = None
        self.last_token_usage: TokenUsageInfo | None = None
        self.error_message: str | None = None

        # --- Environment check state ---
        self.env_check_result: Any = None  # EnvironmentCheckResult
        self.env_check_loading: bool = False
        self.show_env_check_dialog: bool = False

        # --- Update check state ---
        self.update_check_result: Any = None  # UpdateCheckResult
        self.update_dismissed: bool = False
        self.update_in_progress: bool = False

        # --- i18n state ---
        self.locale: str = "zh-CN"

    # ----- Helpers -----

    @property
    def current_session(self) -> ChatSession | None:
        """Return the currently selected session, if any."""
        if not self.current_session_id:
            return None
        for s in self.sessions:
            if s.id == self.current_session_id:
                return s
        return None

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

    def clear_error(self) -> None:
        """Dismiss the current error message."""
        self.error_message = None
