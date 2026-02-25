"""Message list component.

Renders a scrollable list of MessageItem controls for the current session,
with auto-scroll to bottom on new messages and "load earlier" pagination.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t
from misaka.ui.components.message_item import MessageItem
from misaka.ui.components.streaming_message import StreamingMessage

if TYPE_CHECKING:
    from misaka.state import AppState


class MessageList(ft.Column):
    """Scrollable list of chat messages with streaming support."""

    def __init__(
        self,
        state: AppState,
        on_load_more: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_load_more = on_load_more
        self._list_view = ft.ListView(
            expand=True,
            auto_scroll=True,
            spacing=2,
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        )
        self._streaming_msg = StreamingMessage(state)
        self._empty_view = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.CHAT_BUBBLE_OUTLINE,
                        size=48,
                        opacity=0.3,
                    ),
                    ft.Text(
                        t("chat.no_messages"),
                        size=16,
                        weight=ft.FontWeight.W_300,
                        text_align=ft.TextAlign.CENTER,
                        opacity=0.5,
                    ),
                    ft.Text(
                        t("chat.send_to_start"),
                        size=13,
                        text_align=ft.TextAlign.CENTER,
                        opacity=0.3,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        self._build_ui()

    def _build_ui(self) -> None:
        self.controls = [self._empty_view, self._list_view]
        self._sync_controls()

    def _sync_controls(self) -> None:
        """Sync list view controls and visibility from current state."""
        has_messages = bool(self.state.messages) or self.state.is_streaming
        self._empty_view.visible = not has_messages
        self._list_view.visible = has_messages

        items: list[ft.Control] = []

        if self.state.has_more_messages and self._on_load_more:
            items.append(self._build_load_more_button())

        for msg in self.state.messages:
            items.append(MessageItem(msg))

        self._streaming_msg.refresh()
        if self.state.is_streaming:
            items.append(self._streaming_msg)

        self._list_view.controls = items

    def _build_load_more_button(self) -> ft.Control:
        """Build the 'load earlier messages' button shown at the top."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.EXPAND_LESS, size=16, opacity=0.5),
                    ft.Text(
                        t("chat.load_earlier"),
                        size=12,
                        weight=ft.FontWeight.W_500,
                        opacity=0.6,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
            ),
            on_click=lambda e: self._handle_load_more(),
            padding=ft.Padding.symmetric(vertical=8),
            ink=True,
            border_radius=6,
        )

    def _handle_load_more(self) -> None:
        if self._on_load_more:
            self._on_load_more()

    def refresh(self) -> None:
        """Rebuild message list from current state."""
        self._sync_controls()
