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
    from misaka.db.models import Message
    from misaka.state import AppState


class MessageList(ft.Column):
    """Scrollable list of chat messages with streaming support."""

    def __init__(
        self,
        state: AppState,
        on_load_more: Callable[[], None] | None = None,
        on_regenerate: Callable[[str], None] | None = None,
        on_permission_allow: Callable[[], None] | None = None,
        on_permission_allow_always: Callable[[], None] | None = None,
        on_permission_deny: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_load_more = on_load_more
        self._on_regenerate = on_regenerate
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
        self._load_more_button: ft.Control | None = None
        self._was_streaming: bool = False
        self._model_display_name: str = "Claude"
        self._last_session_id_for_model: str | None = None
        self._empty_view = self._build_empty_state()
        self._build_ui()

    def _build_empty_state(self) -> ft.Container:
        """Build the empty state placeholder when there are no messages."""
        icon_circle = ft.Container(
            content=ft.Icon(
                ft.Icons.CHAT_BUBBLE_OUTLINE,
                size=48,
                color=ft.Colors.with_opacity(0.35, ft.Colors.PRIMARY),
            ),
            padding=ft.Padding.all(16),
            border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        )
        title = ft.Text(
            t("chat.no_messages"),
            size=16,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE,
            text_align=ft.TextAlign.CENTER,
        )
        subtitle = ft.Text(
            t("chat.send_to_start"),
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
        )

    def _build_ui(self) -> None:
        self._item_cache.clear()
        self.controls = [self._empty_view, self._list_view]
        self._sync_controls()

    def _resolve_model_display_name_once(self) -> None:
        """Resolve model display name only when session changes. Avoids repeated reads."""
        sid = self.state.current_session_id
        if sid == self._last_session_id_for_model:
            return
        self._last_session_id_for_model = sid
        cli_svc = self.state.get_service("cli_settings_service")
        session = self.state.current_session
        if cli_svc and session and session.model:
            self._model_display_name = cli_svc.get_model_display_name(session.model)
        else:
            self._model_display_name = "Claude"
        self._streaming_msg._assistant_label = self._model_display_name

    def _sync_controls(self) -> None:
        """Sync list view controls and visibility from current state."""
        has_messages = bool(self.state.messages) or self.state.is_streaming
        self._empty_view.visible = not has_messages
        self._list_view.visible = has_messages

        self._resolve_model_display_name_once()

        items: list[ft.Control] = []

        if self.state.has_more_messages and self._on_load_more:
            items.append(self._get_load_more_button())

        for msg in self.state.messages:
            cached = self._item_cache.get(msg.id)
            if cached is None:
                cached = MessageItem(
                    msg,
                    assistant_label=self._model_display_name,
                    on_regenerate=self._on_regenerate,
                )
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

    def _get_load_more_button(self) -> ft.Control:
        """Return cached load-more button to avoid rebuilding on every sync."""
        if self._load_more_button is None:
            self._load_more_button = self._build_load_more_button()
        return self._load_more_button

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

    def append_new_user_message(self, new_message: Message) -> None:
        """Append only the new user message to avoid full rebuild on send.

        Used for fast UI update when sending; falls back to _sync_controls
        when the list was empty (first message).
        """
        has_messages = bool(self.state.messages) or self.state.is_streaming
        self._empty_view.visible = not has_messages
        self._list_view.visible = has_messages

        if not self._list_view.visible or not self._list_view.controls:
            self._sync_controls()
            return

        self._resolve_model_display_name_once()
        cached = self._item_cache.get(new_message.id)
        if cached is None:
            cached = MessageItem(
                new_message,
                assistant_label=self._model_display_name,
                on_regenerate=self._on_regenerate,
            )
            self._item_cache[new_message.id] = cached

        controls = self._list_view.controls
        insert_idx = len(controls)
        if controls and isinstance(controls[-1], PermissionCard):
            insert_idx -= 1
        if self.state.is_streaming and self._streaming_msg in controls:
            insert_idx = controls.index(self._streaming_msg)
        controls.insert(insert_idx, cached)

        if self.state.is_streaming and self._streaming_msg not in controls:
            self._streaming_msg.refresh()
            stream_insert = len(controls)
            if controls and isinstance(controls[-1], PermissionCard):
                stream_insert -= 1
            controls.insert(stream_insert, self._streaming_msg)

        with contextlib.suppress(Exception):
            self._list_view.update()

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
