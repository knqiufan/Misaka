"""Chat page.

The main chat interaction page, combining the chat list panel,
chat view, and right panel with resize handles between them.
This page orchestrates session selection, message sending, and
panel management.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.state import BackgroundStreamStatus
from misaka.ui.chat.components.chat_list import ChatList
from misaka.ui.chat.components.chat_view import ChatView
from misaka.ui.chat.pages.stream_handler import StreamHandler
from misaka.ui.common.theme import get_panel_card_style
from misaka.ui.dialogs.import_session_dialog import ImportSessionDialog
from misaka.ui.file.components.folder_picker import FolderPicker
from misaka.ui.panels.resize_handle import ResizeHandle
from misaka.ui.panels.right_panel import RightPanel

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import ChatSession, FileTreeNode
    from misaka.state import AppState


logger = logging.getLogger(__name__)


class ChatPage(ft.Stack):
    """Full chat page layout with three panels and resize handles."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self._left_width = 260.0
        self._right_width = 300.0
        self._min_panel_width = 180.0
        self._max_panel_width = 500.0

        self._chat_list: ChatList | None = None
        self._chat_view: ChatView | None = None
        self._right_panel: RightPanel | None = None
        self._left_container: ft.Container | None = None
        self._right_container: ft.Container | None = None
        self._left_divider: ft.Control | None = None
        self._left_resize_container: ft.Control | None = None
        self._right_divider: ft.Control | None = None
        self._right_resize_container: ft.Control | None = None
        self._import_dialog: ImportSessionDialog | None = None

        # Drag indicator for visual feedback during resize
        self._drag_indicator: ft.Container | None = None
        self._dragging_side: str | None = None  # "left" or "right"
        self._pending_width: float = 0.0

        self._stream_handler = StreamHandler(
            state=state,
            db=db,
            ui_refresh=self._refresh_stream_ui,
            on_title_changed=self._on_title_changed,
            on_background_status_change=self._on_background_status_change,
        )

        self._file_tree_cache: dict[str, tuple] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        # --- Chat list (left panel) ---
        self._chat_list = ChatList(
            state=self.state,
            on_select=self._on_session_select,
            on_new_chat=self._on_new_chat,
            on_delete=self._on_delete_session,
            on_rename=self._on_rename_session,
            on_archive=self._on_archive_session,
            on_remove_from_list=self._on_remove_from_list,
            on_import=self._on_import_session,
        )

        _panel_style = get_panel_card_style()
        self._left_container = ft.Container(
            content=self._chat_list,
            width=self._left_width,
            visible=self.state.left_panel_open,
            **_panel_style,
        )

        # --- Chat view (center panel) ---
        self._chat_view = ChatView(
            state=self.state,
            on_send=self._on_send_message,
            on_abort=self._on_abort,
            on_model_change=self._on_model_change,
            on_mode_change=self._on_mode_change,
            on_toggle_left_panel=self._toggle_left_panel,
            on_toggle_right_panel=self._toggle_right_panel,
            on_clear_messages=self._on_clear_messages,
            on_load_more=self._on_load_more,
            on_command=self._on_command,
            on_permission_allow=self._on_permission_allow,
            on_permission_allow_always=self._on_permission_allow_always,
            on_permission_deny=self._on_permission_deny,
        )

        # --- Right panel ---
        self._right_panel = RightPanel(
            state=self.state,
            on_file_click=self._on_file_click,
            on_file_select=self._on_file_select,
            on_refresh_file_tree=self._on_refresh_file_tree,
            on_load_folder_children=self._on_load_folder_children,
        )

        self._right_container = ft.Container(
            content=self._right_panel,
            width=self._right_width,
            visible=self.state.right_panel_open,
            **_panel_style,
        )

        # --- Resize handles ---
        left_resize = ResizeHandle(
            on_drag_start=self._on_left_drag_start,
            on_drag=self._on_left_drag,
            on_drag_end=self._on_left_drag_end,
        )
        right_resize = ResizeHandle(
            on_drag_start=self._on_right_drag_start,
            on_drag=self._on_right_drag,
            on_drag_end=self._on_right_drag_end,
        )

        # Store dividers and resize containers as persistent controls
        self._left_resize_container = ft.Container(
            content=left_resize, height=float("inf"),
            visible=self.state.left_panel_open,
        )
        self._left_divider = ft.VerticalDivider(
            width=1,
            color=ft.Colors.TRANSPARENT,
            visible=self.state.left_panel_open,
        )
        self._right_divider = ft.VerticalDivider(
            width=1,
            color=ft.Colors.TRANSPARENT,
            visible=self.state.right_panel_open,
        )
        self._right_resize_container = ft.Container(
            content=right_resize, height=float("inf"),
            visible=self.state.right_panel_open,
        )

        # --- Drag indicator (visual feedback during resize) ---
        self._drag_indicator = ft.Container(
            width=2,
            bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.PRIMARY),
            visible=False,
            left=0,
            top=0,
            bottom=0,
        )

        # --- Main layout ---
        center_container = ft.Container(
            content=self._chat_view,
            expand=True,
            **_panel_style,
        )
        main_row = ft.Row(
            controls=[
                self._left_container,
                self._left_resize_container,
                self._left_divider,
                center_container,
                self._right_divider,
                self._right_resize_container,
                self._right_container,
            ],
            spacing=0,
            expand=True,
        )
        # Horizontal padding for shadow visibility; vertical=0 to match nav_rail height
        main_container = ft.Container(
            content=main_row,
            expand=True,
            padding=ft.Padding.symmetric(horizontal=12, vertical=0),
        )
        # Stack: main content + drag indicator (on top, positioned absolutely)
        self.controls = [
            main_container,
            self._drag_indicator,
        ]

    # ---- Session operations ----

    def _on_session_select(self, session_id: str) -> None:
        """Handle session selection from the chat list."""
        # If clicking the same session that's already selected, do nothing
        if session_id == self.state.current_session_id:
            return

        # Detach current stream to background if switching away from streaming session
        if (self.state.is_streaming
                and self.state.streaming_session_id
                and self.state.streaming_session_id != session_id):
            self._stream_handler.detach_to_background()

        self.state.current_session_id = session_id

        # Check background status of target session
        bg_status = self.state.get_background_status(session_id)
        if bg_status == BackgroundStreamStatus.STREAMING:
            self._stream_handler.reattach_to_foreground(session_id)
        elif bg_status == BackgroundStreamStatus.COMPLETED_UNREAD:
            self.state.mark_background_viewed(session_id)

        # Load messages from DB
        messages, has_more = self.db.get_messages(session_id, limit=10)
        self.state.messages = messages
        self.state.has_more_messages = has_more
        session = self.state.current_session
        if session:
            self.state.sdk_session_id = session.sdk_session_id or None
            self._load_file_tree(session)
        # Refresh UI — targeted refreshes instead of _rebuild_all()
        # Use refresh_selection() for efficient highlight update without rebuilding list
        if self._chat_list:
            self._chat_list.refresh_selection()
        if self._chat_view:
            self._chat_view.refresh()
        if self._right_panel:
            self._right_panel.refresh()
        self.state.update()

    def _on_new_chat(self) -> None:
        """Open folder picker, then create a new chat session."""
        if not self.state.page:
            return
        self._detach_if_streaming()
        picker = FolderPicker(
            page=self.state.page,
            on_select=self._on_new_chat_folder_selected,
        )
        picker.open()

    def _on_new_chat_folder_selected(self, path: str) -> None:
        """Create a new session with the selected working directory."""
        session = self.db.create_session(working_directory=path)
        self.state.sessions = [session] + self.state.sessions
        self.state.current_session_id = session.id
        self.state.messages = []
        self.state.has_more_messages = False
        self.state.tasks = []
        self._stream_handler.reset_stream_state()
        self._scan_file_tree_async(path)
        if self._chat_list:
            self._chat_list.refresh()
        if self._chat_view:
            self._chat_view.refresh()
        self.state.update()

    def _on_delete_session(self, session_id: str) -> None:
        """Delete a session."""
        self._abort_session_if_streaming(session_id)
        self.db.delete_session(session_id)
        self.state.sessions = [s for s in self.state.sessions if s.id != session_id]
        if self.state.current_session_id == session_id:
            self.state.current_session_id = None
            self.state.messages = []
            self.state.tasks = []
            self.state.file_tree_root = None
            self.state.file_tree_nodes = []
        if self._chat_list:
            self._chat_list.refresh()
        if self._chat_view:
            self._chat_view.refresh()
        self.state.update()

    def _on_rename_session(self, session_id: str, new_title: str) -> None:
        """Rename a session."""
        self.db.update_session_title(session_id, new_title)
        for s in self.state.sessions:
            if s.id == session_id:
                s.title = new_title
                break
        if self._chat_list:
            self._chat_list.refresh()
        self.state.update()

    def _on_archive_session(self, session_id: str) -> None:
        """Archive a session."""
        self._abort_session_if_streaming(session_id)
        self.db.update_session_status(session_id, "archived")
        self.state.sessions = [s for s in self.state.sessions if s.id != session_id]
        if self.state.current_session_id == session_id:
            self.state.current_session_id = None
            self.state.messages = []
            self.state.file_tree_root = None
            self.state.file_tree_nodes = []
        if self._chat_list:
            self._chat_list.refresh()
        if self._chat_view:
            self._chat_view.refresh()
        self.state.update()

    def _on_remove_from_list(self, session_id: str) -> None:
        """Remove a session from the list (mark as hidden)."""
        self._abort_session_if_streaming(session_id)
        self.db.update_session_status(session_id, "hidden")
        self.state.sessions = [s for s in self.state.sessions if s.id != session_id]
        if self.state.current_session_id == session_id:
            self.state.current_session_id = None
            self.state.messages = []
            self.state.file_tree_root = None
            self.state.file_tree_nodes = []
        if self._chat_list:
            self._chat_list.refresh()
        if self._chat_view:
            self._chat_view.refresh()
        self.state.update()

    def _on_import_session(self) -> None:
        """Open the import session dialog."""
        if not self.state.page:
            return
        self._import_dialog = ImportSessionDialog(
            page=self.state.page,
            state=self.state,
            on_import=self._on_import_complete,
        )
        self._import_dialog.open()

    def _on_import_complete(self, session_id: str) -> None:
        """Handle completion of session import — select the imported session."""
        self._on_session_select(session_id)

    def _on_load_more(self) -> None:
        """Load earlier messages for the current session."""
        if not self.state.current_session_id or not self.state.messages:
            return
        earliest = self.state.messages[0]
        if earliest._rowid is None:
            return
        older, has_more = self.db.get_messages(
            self.state.current_session_id,
            limit=10,
            before_rowid=earliest._rowid,
        )
        self.state.has_more_messages = has_more
        self.state.messages = older + self.state.messages
        if self._chat_view:
            self._chat_view.refresh_messages()
        self.state.update()

    def _on_command(self, command: str) -> None:
        """Handle an immediate slash command."""
        cmd = command.lstrip("/")

        if cmd == "help":
            self._cmd_help()
        elif cmd == "clear":
            self._on_clear_messages()
        elif cmd == "cost":
            self._cmd_cost()

    def _cmd_help(self) -> None:
        """Insert a help message listing available commands."""
        from misaka.commands import BUILT_IN_COMMANDS

        lines = ["## 可用命令\n"]
        lines.append("### 即时命令")
        for c in BUILT_IN_COMMANDS:
            if c.immediate:
                lines.append(f"- **/{c.name}** — {c.description}")
        lines.append("\n### 提示命令（选择后可补充上下文再发送）")
        for c in BUILT_IN_COMMANDS:
            if not c.immediate:
                lines.append(f"- **/{c.name}** — {c.description}")
        lines.append("\n**提示：** 输入 `/` 浏览命令，使用 Shift+Enter 换行。")

        content_text = "\n".join(lines)
        self._inject_system_message(content_text)

    def _cmd_cost(self) -> None:
        """Insert a token usage summary message."""
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_creation = 0
        total_cost = 0.0
        turn_count = 0

        for msg in self.state.messages:
            usage = msg.parse_token_usage()
            if usage:
                total_input += usage.input_tokens
                total_output += usage.output_tokens
                total_cache_read += usage.cache_read_input_tokens
                total_cache_creation += usage.cache_creation_input_tokens
                if usage.cost_usd:
                    total_cost += usage.cost_usd
                turn_count += 1

        total_tokens = total_input + total_output

        if turn_count == 0:
            content_text = "## Token 用量\n\n暂无用量数据，请先发送一条消息。"
        else:
            rows = [
                "## Token 用量\n",
                "| 指标 | 数量 |",
                "|------|------|",
                f"| 输入 tokens | {total_input:,} |",
                f"| 输出 tokens | {total_output:,} |",
                f"| 缓存读取 | {total_cache_read:,} |",
                f"| 缓存创建 | {total_cache_creation:,} |",
                f"| **总 tokens** | **{total_tokens:,}** |",
                f"| 对话轮次 | {turn_count} |",
            ]
            if total_cost > 0:
                rows.append(f"| **估算费用** | **${total_cost:.4f}** |")
            content_text = "\n".join(rows)

        self._inject_system_message(content_text)

    def _inject_system_message(self, text: str) -> None:
        """Insert a local-only assistant message into the current view."""
        import uuid
        from datetime import datetime, timezone

        from misaka.db.models import Message

        msg = Message(
            id=f"cmd-{uuid.uuid4().hex[:8]}",
            session_id=self.state.current_session_id or "",
            role="assistant",
            content=json.dumps([{"type": "text", "text": text}]),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.state.messages.append(msg)
        if self._chat_view:
            self._chat_view.refresh_messages()
        self.state.update()

    # ---- Message operations ----

    def _on_send_message(self, text: str) -> None:
        """Handle sending a message."""
        if not self.state.current_session_id:
            return
        msg = self._stream_handler.persist_user_message(text)
        self.state.page.run_task(*self._stream_handler.get_send_coroutine(text))
        if msg and self._chat_view:
            self._chat_view.refresh_messages_minimal(msg)
        self.state.update()

        async def _deferred_full_refresh() -> None:
            if self._chat_view:
                self._chat_view.refresh_messages()
            self.state.update()

        self.state.page.run_task(_deferred_full_refresh)

    def _on_abort(self) -> None:
        """Abort the current streaming operation."""
        self.state.page.run_task(*self._stream_handler.get_abort_coroutine())

    def _on_clear_messages(self) -> None:
        """Clear all messages for the current session."""
        if not self.state.current_session_id:
            return
        self._abort_if_streaming()
        self.db.clear_session_messages(self.state.current_session_id)
        self.state.messages = []
        self.state.sdk_session_id = None
        session = self.state.current_session
        if session:
            session.sdk_session_id = ""
        self._stream_handler.reset_stream_state()
        if self._chat_view:
            self._chat_view.refresh_messages()
        self.state.update()

    def _on_model_change(self, model: str) -> None:
        """Handle model selection change."""
        if not self.state.current_session_id:
            return
        session = self.state.current_session
        if session:
            session.model = model
        self.db.update_session_model(self.state.current_session_id, model)
        self.state.update()

    def _on_mode_change(self, mode: str) -> None:
        """Handle mode change."""
        if not self.state.current_session_id:
            return
        self.db.update_session_mode(self.state.current_session_id, mode)
        session = self.state.current_session
        if session:
            session.mode = mode
        if self._chat_view:
            self._chat_view.refresh()
        self.state.update()

    # ---- Panel operations ----

    def _toggle_left_panel(self) -> None:
        self.state.left_panel_open = not self.state.left_panel_open
        visible = self.state.left_panel_open
        if self._left_container:
            self._left_container.visible = visible
        if self._left_divider:
            self._left_divider.visible = visible
        if self._left_resize_container:
            self._left_resize_container.visible = visible
        self.state.update()

    def _toggle_right_panel(self) -> None:
        self.state.right_panel_open = not self.state.right_panel_open
        visible = self.state.right_panel_open
        if self._right_container:
            self._right_container.visible = visible
        if self._right_divider:
            self._right_divider.visible = visible
        if self._right_resize_container:
            self._right_resize_container.visible = visible
        self.state.update()

    # ---- Resize drag handlers (visual feedback during drag) ----

    def _on_left_drag_start(self) -> None:
        """Show drag indicator when left resize starts."""
        self._dragging_side = "left"
        self._pending_width = self._left_width
        if self._drag_indicator:
            self._drag_indicator.visible = True
            self._drag_indicator.update()

    def _on_left_drag(self, global_x: float) -> None:
        """Update drag indicator position during left panel resize."""
        if self._dragging_side != "left":
            return
        # Calculate new width from global x position
        # Account for left padding (12px from container)
        new_width = global_x - 12
        new_width = max(self._min_panel_width, min(self._max_panel_width, new_width))
        self._pending_width = new_width

        # Update indicator position
        if self._drag_indicator:
            # Position indicator at the right edge of the left panel area
            # left = padding + new_width + resize_handle_width(8)
            self._drag_indicator.left = 12 + new_width + 8

    def _on_left_drag_end(self) -> None:
        """Hide indicator and apply final width for left panel."""
        if self._dragging_side != "left":
            return
        # Apply final width
        self._left_width = self._pending_width
        if self._left_container:
            self._left_container.width = self._left_width
            self._left_container.update()

        # Hide indicator
        self._dragging_side = None
        if self._drag_indicator:
            self._drag_indicator.visible = False
            self._drag_indicator.update()

    def _on_right_drag_start(self) -> None:
        """Show drag indicator when right resize starts."""
        self._dragging_side = "right"
        self._pending_width = self._right_width
        if self._drag_indicator:
            self._drag_indicator.visible = True
            self._drag_indicator.update()

    def _on_right_drag(self, global_x: float) -> None:
        """Update drag indicator position during right panel resize."""
        if self._dragging_side != "right":
            return
        # For right panel: width is calculated from right edge
        # Need page width to calculate right edge position
        # Simplified: use the container's offset and calculate relative position
        if not self.state.page:
            return
        page_width = self.state.page.window_width or 800
        # Account for padding (12 on each side = 24 total)
        # Right panel right edge = page_width - 12
        # new_width = right_edge - global_x
        new_width = (page_width - 12) - global_x
        new_width = max(self._min_panel_width, min(self._max_panel_width, new_width))
        self._pending_width = new_width

        # Update indicator position
        if self._drag_indicator:
            # Position indicator at the left edge of the right panel area
            # left = global_x (where the cursor is)
            self._drag_indicator.left = global_x

    def _on_right_drag_end(self) -> None:
        """Hide indicator and apply final width for right panel."""
        if self._dragging_side != "right":
            return
        # Apply final width
        self._right_width = self._pending_width
        if self._right_container:
            self._right_container.width = self._right_width
            self._right_container.update()

        # Hide indicator
        self._dragging_side = None
        if self._drag_indicator:
            self._drag_indicator.visible = False
            self._drag_indicator.update()

    # ---- File and task operations ----

    def _on_file_click(self, path: str) -> None:
        """Handle file click in the file tree."""
        file_svc = self.state.get_service("file_service")
        if not file_svc or not self._right_panel:
            return

        async def _do_preview() -> None:
            try:
                preview = await file_svc.read_file_preview(
                    file_path=path,
                    max_lines=200,
                    base_dir=self.state.file_tree_root,
                )
                self._right_panel.show_file_preview(preview)
                self._right_panel.update()
            except Exception as exc:
                logger.warning("Failed to read file preview for %s: %s", path, exc)

        self.state.page.run_task(_do_preview)

    def _on_file_select(self, path: str) -> None:
        """Handle file/folder selection from right-click menu - insert path into input."""
        if self._chat_view:
            self._chat_view.insert_file_path(path)

    # ---- Permission operations ----

    def _on_permission_allow(self) -> None:
        self._stream_handler.resolve_permission(allow=True, always=False)

    def _on_permission_allow_always(self) -> None:
        self._stream_handler.resolve_permission(allow=True, always=True)

    def _on_permission_deny(self) -> None:
        self._stream_handler.resolve_permission(allow=False)

    # ---- Helpers ----

    def _rebuild_all(self) -> None:
        """Rebuild all sub-components."""
        if self._chat_list:
            self._chat_list.refresh()
        if self._chat_view:
            self._chat_view.refresh()
        if self._right_panel:
            self._right_panel.refresh()

    def refresh(self) -> None:
        self._rebuild_all()

    def set_claude_callbacks(
        self,
        send_callback=None,
        abort_callback=None,
    ) -> None:
        """Set callbacks for Claude service integration."""
        self._stream_handler.set_callbacks(send_callback, abort_callback)

    def _abort_if_streaming(self) -> None:
        if not self.state.is_streaming:
            return
        self.state.page.run_task(self._stream_handler.abort_claude)

    def _detach_if_streaming(self) -> None:
        """Detach the current foreground stream to background instead of aborting."""
        if self.state.is_streaming:
            self._stream_handler.detach_to_background()

    def _abort_session_if_streaming(self, session_id: str) -> None:
        """Abort streaming for a specific session (foreground or background).

        Used for destructive operations (delete, archive, clear).
        """
        # If it's the foreground stream
        if (self.state.is_streaming
                and self.state.streaming_session_id == session_id):
            self.state.page.run_task(self._stream_handler.abort_claude)
            return
        # If it's a background stream
        if session_id in self.state.background_streams:
            self.state.background_streams.pop(session_id, None)
            claude = self.state.get_service("claude_service")
            if claude and claude.is_session_streaming(session_id):
                async def _do_abort() -> None:
                    await claude.abort(session_id)
                self.state.page.run_task(_do_abort)

    def _on_background_status_change(self) -> None:
        """Called when a background stream changes status (started/completed)."""
        if self._chat_list:
            self._chat_list.refresh()
        self.state.update()

    def _refresh_stream_ui(self) -> None:
        """Refresh message list, send/stop button, and connection status after stream events."""
        if self._chat_view:
            self._chat_view.refresh_streaming()
        self.state.update()

    def _load_file_tree(self, session: ChatSession) -> None:
        wd = (session.working_directory or "").strip()
        if not wd:
            self.state.file_tree_root = None
            self.state.file_tree_nodes = []
            return
        self._scan_file_tree_async(wd)

    def _on_refresh_file_tree(self, e: ft.ControlEvent | None = None) -> None:
        """Handle refresh button click - bypass cache and rescan."""
        session = self.state.current_session
        if session and session.working_directory:
            # Clear cache for this directory
            if session.working_directory in self._file_tree_cache:
                del self._file_tree_cache[session.working_directory]
            # Trigger rescan - _scan_file_tree_async already handles async internally
            self._scan_file_tree_async(session.working_directory)

    def _scan_file_tree_async(self, working_dir: str) -> None:
        # Check cache first
        cached = self._file_tree_cache.get(working_dir)
        if cached is not None:
            self.state.file_tree_root, self.state.file_tree_nodes = cached
            self.state.file_tree_expanded_paths.clear()
            if self._right_panel:
                self._right_panel.refresh()
            return

        file_svc = self.state.get_service("file_service")
        if not file_svc:
            return

        async def _do_scan() -> None:
            try:
                self.state.file_tree_loading = True
                self.state.file_tree_expanded_paths.clear()
                self.state.update()
                nodes = await file_svc.scan_directory(working_dir, depth=1)
                self.state.file_tree_root = working_dir
                self.state.file_tree_nodes = nodes
                self._file_tree_cache[working_dir] = (working_dir, nodes)
            except Exception as exc:
                logger.warning("Failed to scan file tree for %s: %s", working_dir, exc)
                self.state.file_tree_root = working_dir
                self.state.file_tree_nodes = []
            finally:
                self.state.file_tree_loading = False
            if self._right_panel:
                self._right_panel.refresh()
            self.state.update()

        self.state.page.run_task(_do_scan)

    def _find_node_by_path(
        self,
        nodes: list[FileTreeNode],
        path: str,
    ) -> FileTreeNode | None:
        """Find a tree node by path, recursing into directory children."""
        for node in nodes:
            if node.path == path:
                return node
            if node.type == "directory" and node.children:
                found = self._find_node_by_path(node.children, path)
                if found is not None:
                    return found
        return None

    def _on_load_folder_children(self, path: str) -> None:
        """Load children for a folder when expanded (lazy load). Schedules async scan."""
        file_svc = self.state.get_service("file_service")
        if not file_svc:
            return

        self.state.file_tree_loading_paths.add(path)
        if self._right_panel:
            self._right_panel.refresh()
        self.state.update()

        async def _do_load() -> None:
            try:
                children = await file_svc.scan_directory(path, depth=1)
                root_nodes = self.state.file_tree_nodes
                if not root_nodes:
                    return
                node = self._find_node_by_path(list(root_nodes), path)
                if node is not None and node.type == "directory":
                    node.children = children
                    self.state.file_tree_expanded_paths.add(path)
            except Exception as exc:
                logger.warning("Failed to load folder children for %s: %s", path, exc)
            finally:
                self.state.file_tree_loading_paths.discard(path)
                if self._right_panel:
                    self._right_panel.refresh()
                self.state.update()

        self.state.page.run_task(_do_load)

    def _on_title_changed(self) -> None:
        """Called by StreamHandler when the session title is auto-synced."""
        if self._chat_list:
            self._chat_list.refresh()
        if self._chat_view:
            self._chat_view.refresh_header_only()
