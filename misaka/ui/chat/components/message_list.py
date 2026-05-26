"""Message list component.

Renders a scrollable list of MessageItem controls for the current session,
with auto-scroll to bottom on new messages and "load earlier" pagination.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.chat.components.message_item import MessageItem
from misaka.ui.chat.components.message_item_shell import MessageItemShell
from misaka.ui.chat.components.permission_card import PermissionCard
from misaka.ui.chat.components.streaming_message import StreamingMessage
from misaka.ui.chat.components.tool_rendering import (
    HEAVY_MESSAGE_TOOL_MIN,
    count_tool_uses,
)
from misaka.utils.perf import perf_timer

if TYPE_CHECKING:
    from misaka.db.models import Message
    from misaka.state import AppState

INITIAL_VISIBLE = 4
STAGED_BATCH_SIZE = 3


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
        self._item_cache: dict[str, ft.Control] = {}
        self._rendered_message_ids: list[str] = []
        self._message_id_index: dict[str, int] = {}
        self._load_more_button: ft.Control | None = None
        self._was_streaming: bool = False
        self._model_display_name: str = "Claude"
        self._last_session_id_for_model: str | None = None
        self._last_scroll_time: float = 0.0
        self._scroll_throttle_sec: float = 0.1
        self._staged_build_token: int = 0
        self._staged_build_in_progress: bool = False
        self._pending_append_messages: list[Message] = []
        self._pending_prepends: list[tuple[list[Message], str]] = []
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
        self._rebuild_message_id_index()
        self.controls = [self._empty_view, self._list_view]
        self._rebuild_from_state()

    def _rebuild_message_id_index(self) -> None:
        """Rebuild the message_id -> position index for O(1) lookups in _find_rag_sources."""
        self._message_id_index = {
            msg.id: i for i, msg in enumerate(self.state.messages)
        }

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

    def _count_tool_uses_for_message(self, message: Message) -> int:
        return count_tool_uses(message.parse_content())

    def _is_heavy_message(self, message: Message) -> bool:
        return (
            message.role == "assistant"
            and self._count_tool_uses_for_message(message) >= HEAVY_MESSAGE_TOOL_MIN
        )

    def _message_weight(self, message: Message) -> int:
        return self._count_tool_uses_for_message(message)

    def _sort_messages_light_first(self, messages: list[Message]) -> list[Message]:
        return sorted(messages, key=self._message_weight)

    def _create_message_item(self, message: Message) -> MessageItem:
        rag_sources = self._find_rag_sources(message)
        item = MessageItem(
            message,
            assistant_label=self._model_display_name,
            on_regenerate=self._on_regenerate,
            rag_sources=rag_sources,
        )
        item.key = message.id
        return item

    def _replace_shell(self, message_id: str, full_item: ft.Control) -> None:
        full_item.key = message_id
        self._item_cache[message_id] = full_item
        for i, ctrl in enumerate(self._list_view.controls):
            if getattr(ctrl, "key", None) == message_id:
                self._list_view.controls[i] = full_item
                break
        self._update_list_view(content_grew=True)

    def _get_or_create_item(
        self,
        message: Message,
        *,
        auto_load_shell: bool = False,
    ) -> ft.Control:
        cached = self._item_cache.get(message.id)
        if cached is not None:
            return cached
        if self._is_heavy_message(message):
            shell: ft.Control = MessageItemShell(
                message,
                assistant_label=self._model_display_name,
                tool_count=self._count_tool_uses_for_message(message),
                build_full_item=lambda m=message: self._create_message_item(m),
                on_replaced=lambda full, mid=message.id: self._replace_shell(mid, full),
            )
            self._item_cache[message.id] = shell
            if auto_load_shell:
                page = self._get_page()
                if page is not None:
                    page.run_task(shell._load_async)  # type: ignore[attr-defined]
            return shell
        item = self._create_message_item(message)
        self._item_cache[message.id] = item
        return item

    def _clear_list_view_fast(self) -> None:
        """Drop old message controls before building a new session."""
        for ctrl in self._list_view.controls:
            with contextlib.suppress(Exception):
                ctrl.content = None
        self._list_view.controls = []
        with contextlib.suppress(Exception):
            self._list_view.update()

    def _find_rag_sources(self, message: Message) -> list:
        """Find RAG sources for an assistant message.

        RAG results are cached by the preceding user message ID.
        For assistant messages, walk backwards to find the user message
        that triggered the RAG retrieval.

        Uses a pre-built message_id -> index mapping for O(1) lookup
        instead of scanning the list each time.
        """
        if message.role != "assistant":
            return []
        cache = self.state.kb.rag_results_cache if self.state.kb else {}
        if not cache:
            return []
        messages = self.state.messages
        idx = self._message_id_index.get(message.id)
        if idx is None:
            return []
        for i in range(idx - 1, -1, -1):
            if messages[i].role == "user":
                return cache.get(messages[i].id, [])
        return []

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

    def _get_page(self) -> ft.Page | None:
        """Return the Flet page when attached, else None."""
        page = getattr(self.state, "page", None)
        if page is not None:
            return page
        with contextlib.suppress(RuntimeError):
            return self.page
        return None

    async def _scroll_list_to_bottom(self) -> None:
        """Scroll the list view to the latest content (Flet 0.80+ async API)."""
        if not self._list_view.page:
            return
        with contextlib.suppress(Exception):
            await self._list_view.scroll_to(offset=-1, duration=0)

    async def _scroll_list_to_anchor(self, anchor_key: str) -> None:
        """Restore scroll position to a message after prepending history."""
        if not self._list_view.page:
            return
        with contextlib.suppress(Exception):
            await self._list_view.scroll_to(scroll_key=anchor_key, duration=0)

    def _schedule_list_scroll(
        self,
        *,
        scroll_to_bottom: bool = False,
        anchor_key: str | None = None,
        throttle_bottom: bool = False,
    ) -> None:
        """Schedule async list scrolling via the page event loop."""
        page = self._get_page()
        if page is None:
            return
        if anchor_key:
            page.run_task(self._scroll_list_to_anchor, anchor_key)
            return
        if not scroll_to_bottom:
            return
        if throttle_bottom:
            now = time.monotonic()
            if now - self._last_scroll_time < self._scroll_throttle_sec:
                return
            self._last_scroll_time = now
        page.run_task(self._scroll_list_to_bottom)

    def _update_list_view(
        self,
        *,
        auto_scroll: bool = False,
        anchor_key: str | None = None,
        content_grew: bool = False,
    ) -> None:
        with perf_timer("list_view_update", 1.0):
            with contextlib.suppress(Exception):
                self._list_view.update()
            if auto_scroll and content_grew:
                self._schedule_list_scroll(
                    scroll_to_bottom=True,
                    throttle_bottom=self.state.is_streaming,
                )
            if anchor_key:
                self._schedule_list_scroll(anchor_key=anchor_key)
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

    def _get_history_insert_index(self) -> int:
        """Index after load-more button for prepending older messages."""
        controls = self._list_view.controls
        if controls and controls[0] is self._get_load_more_button():
            return 1
        return 0

    def _cancel_staged_build(self) -> None:
        """Invalidate any in-flight staged build task."""
        self._staged_build_token += 1
        self._staged_build_in_progress = False

    def _append_trailing_controls(self, items: list[ft.Control]) -> list[ft.Control]:
        """Append streaming message and permission card to a message item list."""
        self._streaming_msg.refresh()
        if self.state.is_streaming:
            items.append(self._streaming_msg)
        permission_card = self._build_permission_card()
        if permission_card is not None:
            items.append(permission_card)
        return items

    def _build_tail_items(self, messages: list[Message]) -> list[ft.Control]:
        """Build list controls for the newest visible message batch."""
        items: list[ft.Control] = []
        if self.state.has_more_messages and self._on_load_more:
            items.append(self._get_load_more_button())
        for i, msg in enumerate(messages):
            is_last = i == len(messages) - 1
            auto_shell = is_last and self._is_heavy_message(msg)
            items.append(self._get_or_create_item(msg, auto_load_shell=auto_shell))
        return self._append_trailing_controls(items)

    def _flush_pending_appends(self, *, scroll_to_bottom: bool = True) -> None:
        """Append messages queued during a staged build."""
        if not self._pending_append_messages:
            return
        pending = self._pending_append_messages
        self._pending_append_messages = []
        for i, msg in enumerate(pending):
            is_last = i == len(pending) - 1
            self.append_message(
                msg,
                scroll_to_bottom=scroll_to_bottom and is_last,
            )

    def _flush_pending_prepends(self, token: int) -> None:
        """Run prepends queued while a session staged build was in progress."""
        if not self._pending_prepends:
            return
        pending = self._pending_prepends
        self._pending_prepends = []
        for older_messages, anchor_key in pending:
            if token != self._staged_build_token:
                return
            if len(older_messages) > STAGED_BATCH_SIZE:
                page = self._get_page()
                if page:
                    page.run_task(
                        self._staged_prepend_older, token, older_messages, anchor_key,
                    )
                else:
                    self._prepend_older_messages_sync(older_messages, anchor_key)
            else:
                self._prepend_older_messages_sync(older_messages, anchor_key)

    async def _staged_build_remaining(
        self,
        token: int,
        remaining: list[Message],
    ) -> None:
        """Insert older messages in batches after the initial tail render."""
        insert_idx = self._get_history_insert_index()
        tail_ids = list(self._rendered_message_ids)
        for start in range(0, len(remaining), STAGED_BATCH_SIZE):
            if token != self._staged_build_token:
                return
            batch = remaining[start : start + STAGED_BATCH_SIZE]
            for msg in batch:
                self._list_view.controls.insert(
                    insert_idx, self._get_or_create_item(msg),
                )
                insert_idx += 1
            built_count = start + len(batch)
            self._rendered_message_ids = (
                [m.id for m in remaining[:built_count]] + tail_ids
            )
            with contextlib.suppress(Exception):
                self._list_view.update()
            await asyncio.sleep(0)

        if token != self._staged_build_token:
            return
        self._staged_build_in_progress = False
        self._flush_pending_prepends(token)
        self._flush_pending_appends()

    async def _staged_prepend_older(
        self,
        token: int,
        older_messages: list[Message],
        anchor_key: str,
    ) -> None:
        """Prepend loaded history in batches while preserving scroll anchor."""
        insert_idx = self._get_history_insert_index()
        older_id_set = {m.id for m in older_messages}
        existing_ids = [
            mid for mid in self._rendered_message_ids if mid not in older_id_set
        ]
        prepended_ids: list[str] = []
        seen_ids = set(self._rendered_message_ids)
        for start in range(0, len(older_messages), STAGED_BATCH_SIZE):
            if token != self._staged_build_token:
                return
            batch = older_messages[start : start + STAGED_BATCH_SIZE]
            for msg in batch:
                if msg.id in seen_ids:
                    continue
                self._list_view.controls.insert(
                    insert_idx, self._get_or_create_item(msg),
                )
                insert_idx += 1
                prepended_ids.append(msg.id)
                seen_ids.add(msg.id)
            if prepended_ids:
                self._rendered_message_ids = prepended_ids + existing_ids
                with contextlib.suppress(Exception):
                    self._list_view.update()
            await asyncio.sleep(0)

        if token == self._staged_build_token:
            self._schedule_list_scroll(anchor_key=anchor_key)

    def _schedule_staged_build_remaining(
        self,
        token: int,
        remaining: list[Message],
    ) -> None:
        page = self._get_page()
        if page is None or not remaining:
            self._staged_build_in_progress = False
            self._flush_pending_appends()
            return
        page.run_task(self._staged_build_remaining, token, remaining)

    def _schedule_staged_prepend(
        self,
        older_messages: list[Message],
        anchor_key: str,
    ) -> None:
        token = self._staged_build_token
        page = self._get_page()
        if page is None:
            self._prepend_older_messages_sync(older_messages, anchor_key)
            return
        page.run_task(self._staged_prepend_older, token, older_messages, anchor_key)

    def _prepend_older_messages_sync(
        self,
        older_messages: list[Message],
        anchor_key: str,
    ) -> None:
        """Synchronously prepend older messages (small batches)."""
        insert_idx = self._get_history_insert_index()
        new_ids: list[str] = []
        for msg in older_messages:
            if msg.id in self._rendered_message_ids:
                continue
            self._list_view.controls.insert(insert_idx, self._get_or_create_item(msg))
            insert_idx += 1
            new_ids.append(msg.id)
        self._rendered_message_ids = new_ids + self._rendered_message_ids
        self._rebuild_message_id_index()
        self._update_list_view(anchor_key=anchor_key, content_grew=True)

    def _rebuild_from_state(self, *, auto_scroll_to_bottom: bool = False) -> None:
        """Rebuild list contents from state as a fallback path."""
        self._cancel_staged_build()
        self._pending_append_messages.clear()
        self._pending_prepends.clear()
        self._sync_visibility()

        self._resolve_model_display_name_once()
        self._rebuild_message_id_index()
        current_ids = {msg.id for msg in self.state.messages}
        self._prune_cache(current_ids)
        self._rendered_message_ids = [msg.id for msg in self.state.messages]
        self._list_view.controls = self._build_items_from_state()
        self._update_list_view(auto_scroll=auto_scroll_to_bottom, content_grew=True)

    def _rebuild_for_session(self, *, auto_scroll_to_bottom: bool = False) -> None:
        """Rebuild after session switch; staged when many messages."""
        self._pending_append_messages.clear()
        self._pending_prepends.clear()
        self._sync_visibility()
        self._clear_list_view_fast()
        self._resolve_model_display_name_once()
        self._rebuild_message_id_index()
        current_ids = {msg.id for msg in self.state.messages}
        self._prune_cache(current_ids)

        messages = self.state.messages
        if len(messages) <= INITIAL_VISIBLE:
            self._staged_build_in_progress = False
            self._rendered_message_ids = [msg.id for msg in messages]
            self._list_view.controls = self._build_items_from_state()
            self._update_list_view(
                auto_scroll=auto_scroll_to_bottom, content_grew=True,
            )
            self._flush_pending_appends(scroll_to_bottom=auto_scroll_to_bottom)
            return

        token = self._staged_build_token
        self._staged_build_in_progress = True
        tail = messages[-INITIAL_VISIBLE:]
        head = messages[:-INITIAL_VISIBLE]

        self._rendered_message_ids = [msg.id for msg in tail]
        self._list_view.controls = self._build_tail_items(tail)
        self._update_list_view(auto_scroll=auto_scroll_to_bottom, content_grew=True)
        self._schedule_staged_build_remaining(token, head)

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
        self._cancel_staged_build()
        self._pending_append_messages.clear()
        self._pending_prepends.clear()
        self._item_cache.clear()
        self._rendered_message_ids.clear()
        self._rebuild_for_session(auto_scroll_to_bottom=bool(self.state.messages))

    def append_message(
        self,
        new_message: Message,
        *,
        scroll_to_bottom: bool = True,
    ) -> None:
        """Append a new message item near the bottom without rebuilding history."""
        if self._staged_build_in_progress:
            self._pending_append_messages.append(new_message)
            return
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
        self._update_list_view(auto_scroll=scroll_to_bottom, content_grew=True)

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
        self._rebuild_message_id_index()

        if self._staged_build_in_progress:
            self._pending_prepends.append((older_messages, anchor_key))
            return

        if len(older_messages) > STAGED_BATCH_SIZE:
            self._schedule_staged_prepend(older_messages, anchor_key)
            return
        self._prepend_older_messages_sync(older_messages, anchor_key)

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
            # Finalize rendering: replace lightweight ft.Text with ft.Markdown
            self._streaming_msg.finalize_render()
            if self._streaming_msg in controls:
                controls.remove(self._streaming_msg)
            self._sync_permission_card()
            if self.state.messages:
                last_message = self.state.messages[-1]
                if last_message.id not in self._rendered_message_ids:
                    self.append_message(last_message)
                    return
            self._sync_visibility()
            self._update_list_view(content_grew=True)
            return

        self._was_streaming = self.state.is_streaming
        self._sync_visibility()
        prev_count = len(self._list_view.controls)
        self._streaming_msg.refresh()
        controls = self._list_view.controls
        if self.state.is_streaming and self._streaming_msg not in controls:
            controls.insert(self._get_message_insert_index(), self._streaming_msg)
        self._sync_permission_card()
        grew = len(controls) > prev_count
        self._update_list_view(auto_scroll=self.state.is_streaming, content_grew=grew)
