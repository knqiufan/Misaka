"""Chat view component.

The main chat area containing the header bar with model/mode selectors,
the message list, streaming message, and message input.
Orchestrates the chat interaction flow.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.chat.components.message_input import MessageInput
from misaka.ui.chat.components.message_list import MessageList
from misaka.ui.common.theme import ACCENT_BLUE, SUCCESS_GREEN, WARNING_AMBER, make_icon_button
from misaka.ui.panels.offset_menu import OffsetMenu, OffsetMenuOption
from misaka.ui.status.connection_status import ConnectionStatus
from misaka.ui.status.update_banner import UpdateBanner

if TYPE_CHECKING:
    from misaka.db.models import Message
    from misaka.state import AppState


class ChatView(ft.Column):
    """Main chat interaction area with header, message list, and input."""

    def __init__(
        self,
        state: AppState,
        on_send: Callable[[str, list | None], None] | None = None,
        on_regenerate: Callable[[str], None] | None = None,
        on_abort: Callable[[], None] | None = None,
        on_model_change: Callable[[str], None] | None = None,
        on_mode_change: Callable[[str], None] | None = None,
        on_toggle_left_panel: Callable[[], None] | None = None,
        on_toggle_right_panel: Callable[[], None] | None = None,
        on_clear_messages: Callable[[], None] | None = None,
        on_load_more: Callable[[], None] | None = None,
        on_command: Callable[[str], None] | None = None,
        on_permission_allow: Callable[[], None] | None = None,
        on_permission_allow_always: Callable[[], None] | None = None,
        on_permission_deny: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_send = on_send
        self._on_regenerate = on_regenerate
        self._on_abort = on_abort
        self._on_model_change = on_model_change
        self._on_mode_change = on_mode_change
        self._on_toggle_left_panel = on_toggle_left_panel
        self._on_toggle_right_panel = on_toggle_right_panel
        self._on_clear_messages = on_clear_messages
        self._on_load_more = on_load_more
        self._on_command = on_command
        self._on_permission_allow = on_permission_allow
        self._on_permission_allow_always = on_permission_allow_always
        self._on_permission_deny = on_permission_deny

        self._message_list: MessageList | None = None
        self._message_input: MessageInput | None = None
        self._connection_status: ConnectionStatus | None = None
        self._mode_dropdown: OffsetMenu | None = None
        self._error_banner: ft.Container | None = None
        self._update_banner: UpdateBanner | None = None
        self._header: ft.Container | None = None
        self._title_text: ft.Text | None = None
        self._welcome_view: ft.Container | None = None
        self._input_container: ft.Container | None = None
        self._clear_btn: ft.Control | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        session = self.state.current_session
        has_session = session is not None

        # --- Header ---
        self._connection_status = ConnectionStatus(
            connected=has_session,
            model=session.model if session else None,
            is_streaming=self.state.is_streaming,
        )

        current_mode = session.mode if session else "agent"
        mode_icons = {
            "agent": ft.Icons.TERMINAL,
            "plan": ft.Icons.LIST,
            "ask": ft.Icons.HELP_OUTLINE,
        }
        mode_colors = {
            "agent": ACCENT_BLUE,
            "plan": WARNING_AMBER,
            "ask": SUCCESS_GREEN,
        }
        self._mode_dropdown = OffsetMenu(
            value=current_mode,
            options=[
                OffsetMenuOption(key="agent", label="Agent"),
                OffsetMenuOption(key="plan", label="Plan"),
                OffsetMenuOption(key="ask", label="Ask"),
            ],
            icon_map=mode_icons,
            color_map=mode_colors,
            width=110,
            menu_width=140,
            offset_y=10,
            on_change=self._handle_mode_change,
        )

        left_toggle = make_icon_button(
            ft.Icons.MENU_ROUNDED,
            tooltip=t("chat.toggle_left_panel"),
            on_click=lambda e: self._on_toggle_left_panel() if self._on_toggle_left_panel else None,
            icon_size=20,
        )

        right_toggle = make_icon_button(
            ft.Icons.VERTICAL_SPLIT_ROUNDED,
            tooltip=t("chat.toggle_right_panel"),
            on_click=lambda e: (
                self._on_toggle_right_panel()
                if self._on_toggle_right_panel else None
            ),
            icon_size=20,
        )

        self._clear_btn = make_icon_button(
            ft.Icons.DELETE_SWEEP_ROUNDED,
            tooltip=t("chat.clear_messages"),
            on_click=lambda e: self._on_clear_messages() if self._on_clear_messages else None,
            icon_size=20,
            visible=has_session,
        )

        # Session title
        title_text = session.title if session else "Misaka"
        self._title_text = ft.Text(
            title_text,
            size=15,
            weight=ft.FontWeight.W_500,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self._header = ft.Container(
            content=ft.Row(
                controls=[
                    left_toggle,
                    ft.Column(
                        controls=[self._title_text],
                        spacing=0,
                        expand=True,
                    ),
                    self._mode_dropdown,
                    self._connection_status,
                    self._clear_btn,
                    right_toggle,
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            border=ft.Border(
                bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
            ),
        )

        # --- Update banner ---
        self._update_banner = UpdateBanner(
            state=self.state,
            on_update=self._handle_update,
            on_dismiss=self._dismiss_update,
        )

        # --- Error banner ---
        self._error_banner = ft.Container(visible=False)
        self._refresh_error_banner()

        # --- Message list ---
        self._message_list = MessageList(
            self.state,
            on_load_more=self._on_load_more,
            on_regenerate=self._on_regenerate,
            on_permission_allow=self._on_permission_allow,
            on_permission_allow_always=self._on_permission_allow_always,
            on_permission_deny=self._on_permission_deny,
        )

        # --- Message input ---
        self._message_input = MessageInput(
            state=self.state,
            on_send=self._on_send,
            on_abort=self._on_abort,
            on_command=self._on_command,
            on_model_change=self._handle_model_change_from_input,
        )

        # --- Welcome view (when no session selected) ---
        self._welcome_view = self._build_welcome_view(visible=not has_session)
        self._message_list.visible = has_session
        self._input_container = ft.Container(
            content=self._message_input,
            visible=has_session,
            border=ft.Border(
                top=ft.BorderSide(
                    1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                ),
            ),
        )

        # --- Assemble ---
        self.controls = [
            self._header,
            self._update_banner,
            self._error_banner,
            self._welcome_view,
            self._message_list,
            self._input_container,
        ]

    def _build_welcome_view(self, *, visible: bool = True) -> ft.Container:
        """Build the welcome placeholder when no session is selected."""
        icon_circle = ft.Container(
            content=ft.Icon(
                ft.Icons.BOLT,
                size=48,
                color=ft.Colors.with_opacity(0.35, ft.Colors.PRIMARY),
            ),
            padding=ft.Padding.all(16),
            border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        )
        title = ft.Text(
            t("app.welcome_title"),
            size=16,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE,
            text_align=ft.TextAlign.CENTER,
        )
        subtitle = ft.Text(
            t("app.welcome_subtitle"),
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )
        inner = ft.Container(
            content=ft.Column(
                controls=[icon_circle, title, subtitle],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=14,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        card = ft.Container(
            content=inner,
            padding=ft.Padding.symmetric(horizontal=40, vertical=270),
            expand=True,
        )
        return ft.Container(
            content=card,
            alignment=ft.Alignment.CENTER,
            expand=True,
            visible=visible,
        )

    def _refresh_error_banner(self) -> None:
        """Update the error banner visibility and content."""
        if not self._error_banner:
            return
        if self.state.error_message:
            self._error_banner.visible = True
            self._error_banner.content = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, color=ft.Colors.ERROR, size=16),
                        ft.Text(
                            self.state.error_message,
                            expand=True,
                            size=12,
                            color=ft.Colors.ERROR,
                        ),
                        make_icon_button(
                            ft.Icons.CLOSE_ROUNDED,
                            on_click=self._dismiss_error,
                            icon_size=14,
                        ),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=6),
                bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ERROR),
            )
        else:
            self._error_banner.visible = False
            self._error_banner.content = ft.Container()

    def _dismiss_error(self, e: ft.ControlEvent) -> None:
        self.state.clear_error()
        self._refresh_error_banner()
        self.state.update()

    def _handle_model_change_from_input(self, model: str) -> None:
        if self._on_model_change and model:
            self._on_model_change(model)

    def _handle_mode_change(self, mode: str) -> None:
        if self._on_mode_change:
            self._on_mode_change(mode)

    def _handle_update(self) -> None:
        """Handle 'Update Now' click from the update banner."""
        update_svc = self.state.get_service('update_check_service')
        if update_svc:
            self.state.update_in_progress = True
            if self._update_banner:
                self._update_banner.refresh()
            self.state.update()

            async def _do_update():
                try:
                    success = await update_svc.perform_update()
                    if success:
                        result = await update_svc.check_for_update()
                        self.state.update_check_result = result
                    self.state.update_in_progress = False
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning("Update failed: %s", exc)
                    self.state.update_in_progress = False
                if self._update_banner:
                    self._update_banner.refresh()
                self.state.update()

            self.state.page.run_task(_do_update)

    def _dismiss_update(self) -> None:
        """Handle dismiss click from the update banner."""
        self.state.update_dismissed = True
        if self._update_banner:
            self._update_banner.refresh()
        self.state.update()

    def refresh(self) -> None:
        """Rebuild the chat view from current state."""
        self._build_ui()

    def _sync_mode_dropdown(self) -> None:
        if not self._mode_dropdown:
            return
        session = self.state.current_session
        new_mode = session.mode if session else "agent"
        if self._mode_dropdown._value == new_mode:
            return
        self._mode_dropdown._value = new_mode
        self._mode_dropdown.content = self._mode_dropdown._build_trigger()
        self._mode_dropdown.items = self._mode_dropdown._build_items()

    def refresh_for_session_change(self) -> None:
        """Refresh session-scoped UI without rebuilding the whole view."""
        session = self.state.current_session
        has_session = session is not None
        if self._title_text:
            self._title_text.value = session.title if session else "Misaka"
        self._sync_mode_dropdown()
        if self._clear_btn:
            self._clear_btn.visible = has_session
        if self._welcome_view:
            self._welcome_view.visible = not has_session
        if self._message_list:
            self._message_list.visible = has_session
            if has_session:
                self._message_list.refresh_for_session_change()
            else:
                self._message_list.clear_messages()
            with contextlib.suppress(Exception):
                self._message_list.update()
        if self._input_container:
            self._input_container.visible = has_session
        if self._message_input:
            self._message_input.refresh()
        if self._connection_status:
            self._connection_status.set_status(
                connected=has_session,
                model=session.model if session else None,
                is_streaming=self.state.is_streaming,
            )
        self._refresh_error_banner()
        if self._header:
            with contextlib.suppress(Exception):
                self._header.update()
        if self._welcome_view:
            with contextlib.suppress(Exception):
                self._welcome_view.update()
        if self._input_container:
            with contextlib.suppress(Exception):
                self._input_container.update()
        if self._error_banner:
            with contextlib.suppress(Exception):
                self._error_banner.update()

    def refresh_header_only(self) -> None:
        """Update only the header title without full rebuild."""
        session = self.state.current_session
        if self._title_text:
            self._title_text.value = session.title if session else "Misaka"
        self._sync_mode_dropdown()
        if self._clear_btn:
            self._clear_btn.visible = session is not None
        if self._connection_status:
            self._connection_status.set_status(
                connected=session is not None,
                model=session.model if session else None,
                is_streaming=self.state.is_streaming,
            )
        if self._header:
            with contextlib.suppress(Exception):
                self._header.update()

    def refresh_messages(self) -> None:
        """Refresh only the message list and streaming state."""
        if self._message_list:
            self._message_list.refresh()
        if self._message_input:
            self._message_input.refresh()
        if self._connection_status:
            self._connection_status.set_status(is_streaming=self.state.is_streaming)
        self._refresh_error_banner()

    def refresh_messages_minimal(self, new_message: Message) -> None:
        """Lightweight update on send: append only the new user message."""
        if self._message_list:
            self._message_list.append_message(new_message)
        if self._message_input:
            self._message_input.refresh()
        if self._connection_status:
            self._connection_status.set_status(is_streaming=self.state.is_streaming)
        self._refresh_error_banner()

    def prepend_older_messages(self, older_messages: list[Message]) -> None:
        """Insert older history at the top without rebuilding the list."""
        if self._message_list:
            self._message_list.prepend_older_messages(older_messages)

    def append_message(self, new_message: Message) -> None:
        """Append a message to the list without rebuilding history."""
        if self._message_list:
            self._message_list.append_message(new_message)

    def remove_message(self, message_id: str) -> None:
        """Remove a single rendered message item."""
        if self._message_list:
            self._message_list.remove_message(message_id)

    def clear_messages_local(self) -> None:
        """Clear rendered messages and show the empty state."""
        if self._message_list:
            self._message_list.clear_messages()
        if self._message_input:
            self._message_input.refresh()
        if self._connection_status:
            self._connection_status.set_status(is_streaming=self.state.is_streaming)

    def refresh_streaming(self) -> None:
        """Refresh streaming-related UI: message list, send/stop button, connection status.

        Used during streaming deltas and when stream completes, so the
        send button correctly reverts from stop (red) to send (primary).
        """
        if self._message_list:
            self._message_list.refresh_streaming()
        if self._message_input:
            self._message_input.refresh()
        if self._connection_status:
            self._connection_status.set_status(is_streaming=self.state.is_streaming)

    def insert_file_path(self, path: str) -> None:
        """Insert a file path into the message input field."""
        if self._message_input:
            self._message_input.insert_at_symbol(path)
