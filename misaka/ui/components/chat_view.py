"""Chat view component.

The main chat area containing the header bar with model/mode selectors,
the message list, streaming message, and message input.
Orchestrates the chat interaction flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t
from misaka.ui.components.connection_status import ConnectionStatus
from misaka.ui.components.message_input import MessageInput
from misaka.ui.components.message_list import MessageList
from misaka.ui.components.update_banner import UpdateBanner

if TYPE_CHECKING:
    from misaka.state import AppState


# Available models: (value, display_label)
_MODELS = [
    ("sonnet", "Sonnet 4.5"),
    ("opus", "Opus 4.6"),
    ("haiku", "Haiku 4.5"),
]

_MODEL_VALUES = [m[0] for m in _MODELS]

# Available modes
_MODES = [
    ("code", "Code", ft.Colors.BLUE),
    ("plan", "Plan", ft.Colors.ORANGE),
    ("ask", "Ask", ft.Colors.GREEN),
]


class ChatView(ft.Column):
    """Main chat interaction area with header, message list, and input."""

    def __init__(
        self,
        state: AppState,
        on_send: Callable[[str], None] | None = None,
        on_abort: Callable[[], None] | None = None,
        on_model_change: Callable[[str], None] | None = None,
        on_mode_change: Callable[[str], None] | None = None,
        on_toggle_left_panel: Callable[[], None] | None = None,
        on_toggle_right_panel: Callable[[], None] | None = None,
        on_clear_messages: Callable[[], None] | None = None,
        on_open_folder: Callable[[], None] | None = None,
        on_load_more: Callable[[], None] | None = None,
        on_command: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_send = on_send
        self._on_abort = on_abort
        self._on_model_change = on_model_change
        self._on_mode_change = on_mode_change
        self._on_toggle_left_panel = on_toggle_left_panel
        self._on_toggle_right_panel = on_toggle_right_panel
        self._on_clear_messages = on_clear_messages
        self._on_open_folder = on_open_folder
        self._on_load_more = on_load_more
        self._on_command = on_command

        self._message_list: MessageList | None = None
        self._message_input: MessageInput | None = None
        self._connection_status: ConnectionStatus | None = None
        self._model_dropdown: ft.Dropdown | None = None
        self._mode_buttons: list[ft.Control] = []
        self._error_banner: ft.Container | None = None
        self._update_banner: UpdateBanner | None = None
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

        # Model selector
        from misaka.ui.theme import make_dropdown as _mdd
        current_model = session.model if session else _MODELS[0][0]
        self._model_dropdown = _mdd(
            value=current_model if current_model in _MODEL_VALUES else _MODELS[0][0],
            options=[ft.dropdown.Option(key=m[0], text=m[1]) for m in _MODELS],
            dense=True,
            content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            width=200,
            on_select=self._handle_model_change,
            text_size=12,
        )

        # Mode toggle buttons (pill-shaped)
        current_mode = session.mode if session else "code"
        self._mode_buttons = []
        for mode_id, mode_label, mode_color in _MODES:
            is_active = current_mode == mode_id
            btn = ft.Container(
                content=ft.Text(
                    mode_label,
                    size=11,
                    weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.NORMAL,
                    color=ft.Colors.WHITE if is_active else ft.Colors.ON_SURFACE_VARIANT,
                ),
                bgcolor=mode_color if is_active else ft.Colors.TRANSPARENT,
                border_radius=12,
                padding=ft.Padding.symmetric(horizontal=10, vertical=3),
                on_click=lambda e, m=mode_id: self._handle_mode_change(m),
                ink=True,
                border=ft.Border.all(
                    1,
                    mode_color if is_active else ft.Colors.with_opacity(0.3, ft.Colors.OUTLINE),
                ),
            )
            self._mode_buttons.append(btn)

        # Left panel toggle
        left_toggle = ft.IconButton(
            icon=ft.Icons.MENU,
            tooltip=t("chat.toggle_left_panel"),
            on_click=lambda e: self._on_toggle_left_panel() if self._on_toggle_left_panel else None,
            icon_size=20,
            style=ft.ButtonStyle(padding=6),
        )

        # Right panel toggle
        right_toggle = ft.IconButton(
            icon=ft.Icons.VERTICAL_SPLIT,
            tooltip=t("chat.toggle_right_panel"),
            on_click=lambda e: self._on_toggle_right_panel() if self._on_toggle_right_panel else None,
            icon_size=20,
            style=ft.ButtonStyle(padding=6),
        )

        # Clear messages button
        clear_btn = ft.IconButton(
            icon=ft.Icons.DELETE_SWEEP,
            tooltip=t("chat.clear_messages"),
            on_click=lambda e: self._on_clear_messages() if self._on_clear_messages else None,
            icon_size=20,
            style=ft.ButtonStyle(padding=6),
            visible=has_session,
        )

        # Folder picker button
        folder_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip=t("chat.open_folder"),
            on_click=lambda e: self._on_open_folder() if self._on_open_folder else None,
            icon_size=20,
            style=ft.ButtonStyle(padding=6),
            visible=has_session,
        )

        # Session title + working directory
        title_text = session.title if session else "Misaka"
        working_dir = session.working_directory if session else ""

        title_col_controls = [
            ft.Text(
                title_text,
                size=16,
                weight=ft.FontWeight.W_500,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ]
        if working_dir:
            title_col_controls.append(
                ft.Text(
                    working_dir,
                    size=10,
                    opacity=0.5,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            )

        header = ft.Container(
            content=ft.Row(
                controls=[
                    left_toggle,
                    ft.Column(
                        controls=title_col_controls,
                        spacing=0,
                        expand=True,
                    ),
                    folder_btn,
                    ft.Row(
                        controls=self._mode_buttons,
                        spacing=4,
                    ),
                    self._model_dropdown,
                    self._connection_status,
                    clear_btn,
                    right_toggle,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
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
        )

        # --- Message input ---
        self._message_input = MessageInput(
            state=self.state,
            on_send=self._on_send,
            on_abort=self._on_abort,
            on_command=self._on_command,
        )

        # --- Welcome view (when no session selected) ---
        welcome_view = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.SMART_TOY, size=64, opacity=0.2),
                    ft.Text(
                        t("app.welcome_title"),
                        size=24,
                        weight=ft.FontWeight.W_300,
                        text_align=ft.TextAlign.CENTER,
                        opacity=0.5,
                    ),
                    ft.Text(
                        t("app.welcome_subtitle"),
                        size=14,
                        text_align=ft.TextAlign.CENTER,
                        opacity=0.3,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            visible=not has_session,
        )

        # --- Assemble ---
        self.controls = [
            header,
            ft.Divider(height=1),
            self._update_banner,
            self._error_banner,
            self._message_list if has_session else welcome_view,
            ft.Divider(height=1) if has_session else ft.Container(height=0),
            ft.Container(
                content=self._message_input,
                visible=has_session,
            ),
        ]

    def _refresh_error_banner(self) -> None:
        """Update the error banner visibility and content."""
        if not self._error_banner:
            return
        if self.state.error_message:
            self._error_banner.visible = True
            self._error_banner.content = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.ERROR, color=ft.Colors.ERROR, size=18),
                        ft.Text(
                            self.state.error_message,
                            expand=True,
                            size=13,
                            color=ft.Colors.ERROR,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=16,
                            on_click=self._dismiss_error,
                            style=ft.ButtonStyle(padding=4),
                        ),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ERROR),
            )
        else:
            self._error_banner.visible = False
            self._error_banner.content = ft.Container()

    def _dismiss_error(self, e: ft.ControlEvent) -> None:
        self.state.clear_error()
        self._refresh_error_banner()
        self.state.update()

    def _handle_model_change(self, e: ft.ControlEvent) -> None:
        model = e.data or e.control.value
        if self._on_model_change and model:
            self._on_model_change(model)

    def _handle_mode_change(self, mode: str) -> None:
        if self._on_mode_change:
            self._on_mode_change(mode)

    def _handle_update(self) -> None:
        """Handle 'Update Now' click from the update banner."""
        if hasattr(self.state, 'services') and self.state.services:
            update_svc = getattr(self.state.services, 'update_check_service', None)
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
                    except Exception:
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

    def refresh_messages(self) -> None:
        """Refresh only the message list and streaming state."""
        if self._message_list:
            self._message_list.refresh()
        if self._message_input:
            self._message_input.refresh()
        if self._connection_status:
            self._connection_status.set_status(is_streaming=self.state.is_streaming)
        self._refresh_error_banner()
