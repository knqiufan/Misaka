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
            auto_scroll=False,
            spacing=2,
            padding=ft.Padding.symmetric(horizontal=4, vertical=8),
        )
        self._streaming_msg = StreamingMessage(state)
        self._item_cache: dict[str, MessageItem] = {}
        self._rendered_message_ids: list[str] = []
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
        self._rendered_message_ids.clear()
        self.controls = [self._empty_view, self._list_view]
        self._rebuild_from_state()

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

    def _sync_visibility(self) -> None:
        """Sync empty-state and list visibility from current state."""
        has_messages = bool(self.state.messages) or self.state.is_streaming
        self._empty_view.visible = not has_messages
        self._list_view.visible = has_messages

    def _get_or_create_item(self, message: Message) -> MessageItem:
        cached = self._item_cache.get(message.id)
        if cached is None:
            cached = MessageItem(
                message,
                assistant_label=self._model_display_name,
                on_regenerate=self._on_regenerate,
            )
            cached.key = message.id
            self._item_cache[message.id] = cached
        return cached

    def _prune_cache(self, current_ids: set[str]) -> None:
        stale_ids = [mid for mid in self._item_cache if mid not in current_ids]
        for mid in stale_ids:
            self._item_cache.pop(mid, None)

    def _build_items_from_state(self) -> list[ft.Control]:
        items: list[ft.Control] = []
        if self.state.has_more_messages and self._on_load_more:
            items.append(self._get_load_more_button())
        for msg in self.state.messages:
            items.append(self._get_or_create_item(msg))
        self._streaming_msg.refresh()
        if self.state.is_streaming:
            items.append(self._streaming_msg)
        permission_card = self._build_permission_card()
        if permission_card is not None:
            items.append(permission_card)
        return items

    def _update_list_view(
        self,
        *,
        auto_scroll: bool = False,
        anchor_key: str | None = None,
    ) -> None:
        with contextlib.suppress(Exception):
            self._list_view.update()
        if auto_scroll:
            with contextlib.suppress(Exception):
                self._list_view.scroll_to(offset=-1, duration=0)
        if anchor_key:
            with contextlib.suppress(Exception):
                self._list_view.scroll_to(key=anchor_key, duration=0)
        try:
            if self._empty_view.page:
                with contextlib.suppress(Exception):
                    self._empty_view.update()
        except RuntimeError:
            pass

    def _build_permission_card(self) -> PermissionCard | None:
        if not (
            self.state.pending_permission
            and self._on_permission_allow
            and self._on_permission_allow_always
            and self._on_permission_deny
        ):
            return None
        return PermissionCard(
            permission=self.state.pending_permission,
            on_allow=self._on_permission_allow,
            on_allow_always=self._on_permission_allow_always,
            on_deny=self._on_permission_deny,
        )

    def _sync_load_more_button(self) -> None:
        controls = self._list_view.controls
        has_button = bool(controls) and controls[0] is self._get_load_more_button()
        needs_button = self.state.has_more_messages and self._on_load_more is not None
        if needs_button and not has_button:
            controls.insert(0, self._get_load_more_button())
        elif has_button and not needs_button:
            controls.pop(0)

    def _sync_permission_card(self) -> None:
        controls = self._list_view.controls
        has_perm_card = bool(controls) and isinstance(controls[-1], PermissionCard)
        permission_card = self._build_permission_card()
        if permission_card and not has_perm_card:
            controls.append(permission_card)
        elif permission_card and has_perm_card:
            controls[-1] = permission_card
        elif has_perm_card:
            controls.pop()

    def _get_message_insert_index(self) -> int:
        controls = self._list_view.controls
        insert_idx = len(controls)
        if controls and isinstance(controls[-1], PermissionCard):
            insert_idx -= 1
        if self._streaming_msg in controls:
            insert_idx = min(insert_idx, controls.index(self._streaming_msg))
        return insert_idx

    def _rebuild_from_state(self, *, auto_scroll_to_bottom: bool = False) -> None:
        """Rebuild list contents from state as a fallback path."""
        self._sync_visibility()

        self._resolve_model_display_name_once()
        current_ids = {msg.id for msg in self.state.messages}
        self._prune_cache(current_ids)
        self._rendered_message_ids = [msg.id for msg in self.state.messages]
        self._list_view.controls = self._build_items_from_state()
        self._update_list_view(auto_scroll=auto_scroll_to_bottom)

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
        self._rebuild_from_state()

    def refresh_for_session_change(self) -> None:
        """Refresh list after switching sessions."""
        self._item_cache.clear()
        self._rendered_message_ids.clear()
        self._rebuild_from_state(auto_scroll_to_bottom=bool(self.state.messages))

    def append_message(
        self,
        new_message: Message,
        *,
        scroll_to_bottom: bool = True,
    ) -> None:
        """Append a new message item near the bottom without rebuilding history."""
        self._sync_visibility()
        if not self._list_view.visible:
            self._rebuild_from_state(auto_scroll_to_bottom=scroll_to_bottom)
            return
        self._resolve_model_display_name_once()
        self._sync_load_more_button()
        cached = self._get_or_create_item(new_message)
        controls = self._list_view.controls
        if new_message.id in self._rendered_message_ids and cached in controls:
            self._update_list_view(auto_scroll=scroll_to_bottom)
            return
        controls.insert(self._get_message_insert_index(), cached)
        self._rendered_message_ids.append(new_message.id)
        if self.state.is_streaming and self._streaming_msg not in controls:
            self._streaming_msg.refresh()
            controls.insert(self._get_message_insert_index(), self._streaming_msg)
        self._sync_permission_card()
        self._update_list_view(auto_scroll=scroll_to_bottom)

    def append_new_user_message(self, new_message: Message) -> None:
        """Append only the new user message to avoid full rebuild on send.

        Used for fast UI update when sending; falls back to _sync_controls
        when the list was empty (first message).
        """
        self.append_message(new_message)

    def prepend_older_messages(self, older_messages: list[Message]) -> None:
        """Insert older messages at the top while keeping the current anchor."""
        if not older_messages:
            return
        self._sync_visibility()
        if not self._list_view.visible or not self._rendered_message_ids:
            self._rebuild_from_state()
            return
        self._resolve_model_display_name_once()
        self._sync_load_more_button()
        anchor_key = self._rendered_message_ids[0]
        insert_idx = 1 if self.state.has_more_messages and self._on_load_more else 0
        new_ids: list[str] = []
        for msg in older_messages:
            if msg.id in self._rendered_message_ids:
                continue
            self._list_view.controls.insert(insert_idx, self._get_or_create_item(msg))
            insert_idx += 1
            new_ids.append(msg.id)
        self._rendered_message_ids = new_ids + self._rendered_message_ids
        self._update_list_view(anchor_key=anchor_key)

    def remove_message(self, message_id: str) -> None:
        """Remove a rendered message item without rebuilding the full list."""
        if message_id not in self._rendered_message_ids:
            return
        cached = self._item_cache.get(message_id)
        if cached and cached in self._list_view.controls:
            self._list_view.controls.remove(cached)
        self._rendered_message_ids = [
            mid for mid in self._rendered_message_ids if mid != message_id
        ]
        self._item_cache.pop(message_id, None)
        self._sync_visibility()
        self._update_list_view()

    def clear_messages(self) -> None:
        """Clear all rendered messages and switch to the empty state."""
        self._rendered_message_ids.clear()
        self._item_cache.clear()
        self._list_view.controls = []
        self._sync_visibility()
        self._update_list_view()

    def refresh_streaming(self) -> None:
        """Refresh only the streaming message and permission card.

        Skips rebuilding historical MessageItems — much cheaper than
        a full refresh() during streaming deltas.
        """
        # Detect streaming end - if was streaming but now not, do full sync
        # to ensure the final message appears as MessageItem
        if self._was_streaming and not self.state.is_streaming:
            self._was_streaming = False
            controls = self._list_view.controls
            if self._streaming_msg in controls:
                controls.remove(self._streaming_msg)
            self._sync_permission_card()
            if self.state.messages:
                last_message = self.state.messages[-1]
                if last_message.id not in self._rendered_message_ids:
                    self.append_message(last_message)
                    return
            self._sync_visibility()
            self._update_list_view()
            return

        self._was_streaming = self.state.is_streaming
        self._sync_visibility()
        self._streaming_msg.refresh()
        controls = self._list_view.controls
        if self.state.is_streaming and self._streaming_msg not in controls:
            controls.insert(self._get_message_insert_index(), self._streaming_msg)
        self._sync_permission_card()
        self._update_list_view(auto_scroll=self.state.is_streaming)
