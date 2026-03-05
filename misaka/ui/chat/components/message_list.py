"""Message list component.

Renders a scrollable list of MessageItem controls for the current session,
with auto-scroll to bottom on new messages and "load earlier" pagination.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.chat.components.message_item import MessageItem
from misaka.ui.chat.components.permission_card import PermissionCard
from misaka.ui.chat.components.streaming_message import StreamingMessage

if TYPE_CHECKING:
    from misaka.state import AppState


class MessageList(ft.Column):
    """Scrollable list of chat messages with streaming support."""

    def __init__(
        self,
        state: AppState,
        on_load_more: Callable[[], None] | None = None,
        on_permission_allow: Callable[[], None] | None = None,
        on_permission_allow_always: Callable[[], None] | None = None,
        on_permission_deny: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_load_more = on_load_more
        self._on_permission_allow = on_permission_allow
        self._on_permission_allow_always = on_permission_allow_always
        self._on_permission_deny = on_permission_deny
        self._list_view = ft.ListView(
            expand=True,
            auto_scroll=True,
            spacing=2,
            padding=ft.Padding.symmetric(horizontal=4, vertical=8),
        )
        self._streaming_msg = StreamingMessage(state)
        self._item_cache: dict[str, MessageItem] = {}
        self._was_streaming: bool = False
        self._empty_view = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.CHAT_BUBBLE_OUTLINE,
                        size=40,
                        opacity=0.15,
                    ),
                    ft.Text(
                        t("chat.no_messages"),
                        size=15,
                        weight=ft.FontWeight.W_300,
                        text_align=ft.TextAlign.CENTER,
                        opacity=0.4,
                    ),
                    ft.Text(
                        t("chat.send_to_start"),
                        size=12,
                        text_align=ft.TextAlign.CENTER,
                        opacity=0.25,
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
        self._item_cache.clear()
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
            cached = self._item_cache.get(msg.id)
            if cached is None:
                cached = MessageItem(msg)
                self._item_cache[msg.id] = cached
            items.append(cached)

        self._streaming_msg.refresh()
        if self.state.is_streaming:
            items.append(self._streaming_msg)

        if (
            self.state.pending_permission
            and self._on_permission_allow
            and self._on_permission_allow_always
            and self._on_permission_deny
        ):
            items.append(PermissionCard(
                permission=self.state.pending_permission,
                on_allow=self._on_permission_allow,
                on_allow_always=self._on_permission_allow_always,
                on_deny=self._on_permission_deny,
            ))

        self._list_view.controls = items

    def _build_load_more_button(self) -> ft.Control:
        """Build the 'load earlier messages' button shown at the top."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.EXPAND_LESS_ROUNDED, size=14, opacity=0.4),
                    ft.Text(
                        t("chat.load_earlier"),
                        size=11,
                        weight=ft.FontWeight.W_500,
                        opacity=0.5,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
            ),
            on_click=lambda e: self._handle_load_more(),
            padding=ft.Padding.symmetric(vertical=8),
            ink=True,
            border_radius=8,
        )

    def _handle_load_more(self) -> None:
        if self._on_load_more:
            self._on_load_more()

    def refresh(self) -> None:
        """Rebuild message list from current state."""
        self._sync_controls()

    def refresh_streaming(self) -> None:
        """Refresh only the streaming message and permission card.

        Skips rebuilding historical MessageItems — much cheaper than
        a full refresh() during streaming deltas.
        """
        # Detect streaming end - if was streaming but now not, do full sync
        # to ensure the final message appears as MessageItem
        if self._was_streaming and not self.state.is_streaming:
            self._was_streaming = self.state.is_streaming
            self._sync_controls()
            with contextlib.suppress(Exception):
                self._list_view.update()
            return

        self._was_streaming = self.state.is_streaming
        self._streaming_msg.refresh()

        # Handle permission card: check if we need to add/remove it
        controls = self._list_view.controls
        has_perm_card = controls and isinstance(controls[-1], PermissionCard)
        needs_perm_card = (
            self.state.pending_permission
            and self._on_permission_allow
            and self._on_permission_allow_always
            and self._on_permission_deny
        )

        if needs_perm_card and not has_perm_card:
            controls.append(PermissionCard(
                permission=self.state.pending_permission,
                on_allow=self._on_permission_allow,
                on_allow_always=self._on_permission_allow_always,
                on_deny=self._on_permission_deny,
            ))
        elif has_perm_card and not needs_perm_card:
            controls.pop()

        # Ensure streaming message is in the list
        if self.state.is_streaming and self._streaming_msg not in controls:
            # Insert before permission card if present
            insert_idx = len(controls)
            if controls and isinstance(controls[-1], PermissionCard):
                insert_idx -= 1
            controls.insert(insert_idx, self._streaming_msg)

        with contextlib.suppress(Exception):
            self._list_view.update()
