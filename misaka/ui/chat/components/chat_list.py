"""Chat list panel component.

Displays a scrollable list of chat sessions in the left sidebar
with search filtering, new-chat button, and context menu support.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.state import BackgroundStreamStatus
from misaka.ui.common.context_menu import ContextMenuItem, FloatingContextMenu

if TYPE_CHECKING:
    from misaka.db.models import ChatSession
    from misaka.state import AppState


# Module-level context menu instance
_context_menu = FloatingContextMenu()


class ChatList(ft.Column):
    """Scrollable list of chat sessions with search and create."""

    def __init__(
        self,
        state: AppState,
        on_select: Callable[[str], None] | None = None,
        on_new_chat: Callable[[], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_rename: Callable[[str, str], None] | None = None,
        on_remove_from_list: Callable[[str], None] | None = None,
        on_import: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_select = on_select
        self._on_new_chat = on_new_chat
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_remove_from_list = on_remove_from_list
        self._on_import = on_import
        self._search_query = ""
        self._search_field: ft.TextField | None = None
        self._session_list: ft.ListView | None = None
        self._pulse_phase: bool = False
        self._pulse_timer_running: bool = False
        self._item_cache: dict[str, ft.Control] = {}
        self._last_selected_id: str | None = None
        self._search_debounce_timer: asyncio.TimerHandle | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        from misaka.ui.common.theme import make_icon_button
        from misaka.ui.common.theme import make_text_field as _mtf
        self._search_field = _mtf(
            hint_text=t("chat.search_sessions"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_change=self._on_search,
        )

        is_project_mode = self.state.chat_group_mode == "project"
        self._group_toggle_btn = make_icon_button(
            ft.Icons.FOLDER_OUTLINED if is_project_mode else ft.Icons.CALENDAR_TODAY,
            tooltip=t("chat.group_by_date") if is_project_mode else t("chat.group_by_project"),
            on_click=self._toggle_group_mode,
        )

        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        t("chat.chats"),
                        size=15,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    self._group_toggle_btn,
                    make_icon_button(
                        ft.Icons.DOWNLOAD_ROUNDED,
                        tooltip=t("chat.import_session"),
                        on_click=self._handle_import,
                    ),
                    make_icon_button(
                        ft.Icons.ADD_ROUNDED,
                        tooltip=t("chat.new_chat"),
                        on_click=self._handle_new_chat,
                        icon_size=20,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=14, right=4, top=10, bottom=4),
        )

        search_bar = ft.Container(
            content=self._search_field,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        )

        self._session_list = ft.ListView(
            expand=True,
            spacing=2,
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        )

        list_surface = ft.GestureDetector(
            content=self._session_list,
            on_tap=lambda _: _context_menu.dismiss(),
        )

        self.controls = [
            header,
            search_bar,
            list_surface,
        ]

        self._refresh_list()

    def _refresh_list(self) -> None:
        """Rebuild the session list items from state."""
        if not self._session_list:
            return

        sessions = self._get_filtered_sessions()

        if not sessions:
            msg = t("chat.no_matching_sessions") if self._search_query else t("chat.no_sessions")
            self._session_list.controls = [
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHAT_BUBBLE_OUTLINE,
                                size=28,
                                opacity=0.2,
                            ),
                            ft.Text(
                                msg,
                                italic=True,
                                size=12,
                                opacity=0.4,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=32,
                )
            ]
            return

        if self.state.chat_group_mode == "project":
            grouped = self._group_by_project(sessions)
        else:
            grouped = self._group_by_date(sessions)
        controls: list[ft.Control] = []
        for label, group in grouped:
            if label:
                controls.append(
                    ft.Container(
                        content=ft.Text(
                            label,
                            size=10,
                            weight=ft.FontWeight.W_600,
                            opacity=0.35,
                        ),
                        padding=ft.Padding.only(left=12, top=12, bottom=4),
                    )
                )
            for s in group:
                item = self._build_session_item(s)
                self._item_cache[s.id] = item
                controls.append(item)

        self._session_list.controls = controls

    @staticmethod
    def _group_by_date(
        sessions: list[ChatSession],
    ) -> list[tuple[str, list[ChatSession]]]:
        """Group sessions into Today / Yesterday / Earlier buckets."""
        today = date.today()
        buckets: dict[str, list[ChatSession]] = {
            "today": [],
            "yesterday": [],
            "earlier": [],
        }
        for s in sessions:
            try:
                if s.updated_at and "T" in s.updated_at:
                    d = datetime.fromisoformat(s.updated_at.replace("Z", "+00:00")).date()
                else:
                    d = None
            except (ValueError, TypeError):
                d = None

            if d == today:
                buckets["today"].append(s)
            elif d and (today - d).days == 1:
                buckets["yesterday"].append(s)
            else:
                buckets["earlier"].append(s)

        result: list[tuple[str, list[ChatSession]]] = []
        if buckets["today"]:
            result.append((t("chat.today"), buckets["today"]))
        if buckets["yesterday"]:
            result.append((t("chat.yesterday"), buckets["yesterday"]))
        if buckets["earlier"]:
            result.append((t("chat.earlier"), buckets["earlier"]))
        # If only one group, skip the header
        if len(result) == 1:
            return [("", result[0][1])]
        return result

    @staticmethod
    def _group_by_project(
        sessions: list[ChatSession],
    ) -> list[tuple[str, list[ChatSession]]]:
        """Group sessions by working directory (project)."""
        buckets: dict[str, list[ChatSession]] = {}
        no_project_key = ""
        for s in sessions:
            wd = (s.working_directory or "").strip()
            label = (s.project_name or os.path.basename(wd) or wd) if wd else no_project_key
            buckets.setdefault(label, []).append(s)

        result: list[tuple[str, list[ChatSession]]] = []
        no_project = buckets.pop(no_project_key, None)
        for label in sorted(buckets):
            result.append((label, buckets[label]))
        if no_project:
            result.append((t("chat.no_project"), no_project))
        if len(result) == 1:
            return [("", result[0][1])]
        return result

    def _toggle_group_mode(self, e: ft.ControlEvent) -> None:
        """Switch between date and project grouping."""
        new_mode = "date" if self.state.chat_group_mode == "project" else "project"
        self.state.chat_group_mode = new_mode

        settings_svc = self.state.get_service("settings")
        if settings_svc:
            from misaka.config import SettingKeys
            settings_svc.set(SettingKeys.CHAT_GROUP_MODE, new_mode)

        is_project = new_mode == "project"
        self._group_toggle_btn.icon = (
            ft.Icons.FOLDER_OUTLINED if is_project else ft.Icons.CALENDAR_TODAY
        )
        self._group_toggle_btn.tooltip = (
            t("chat.group_by_date") if is_project else t("chat.group_by_project")
        )

        self._item_cache.clear()
        self._refresh_list()
        if self._session_list:
            self._session_list.update()

    def _get_filtered_sessions(self) -> list[ChatSession]:
        """Return sessions filtered by search query and status (exclude hidden)."""
        sessions = [s for s in self.state.sessions if s.status != "hidden"]
        if not self._search_query:
            return sessions
        q = self._search_query.lower()
        return [
            s for s in sessions
            if q in s.title.lower()
            or q in (s.project_name or "").lower()
        ]

    def _build_session_item(self, session: ChatSession) -> ft.Control:
        """Build a single session list item with refined minimal design."""
        from misaka.ui.common.theme import ACCENT_BLUE, SUCCESS_GREEN, WARNING_AMBER

        is_selected = session.id == self.state.current_session_id

        # Background stream status dot (pulsing when streaming)
        bg_status = self.state.get_background_status(session.id)
        status_dot: ft.Control | None = None
        if bg_status is not None:
            dot_color = (
                WARNING_AMBER
                if bg_status == BackgroundStreamStatus.STREAMING
                else SUCCESS_GREEN
            )
            status_dot = ft.Container(
                width=6,
                height=6,
                border_radius=3,
                bgcolor=dot_color,
                opacity=0.3 if self._pulse_phase else 1.0,
                animate_opacity=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
                margin=ft.Margin.only(right=6),
            )

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
        icon_name = mode_icons.get(session.mode, ft.Icons.CHAT_BUBBLE_OUTLINE)
        icon_color = mode_colors.get(session.mode, "#6b7280")

        # Mode indicator: icon per mode (agent=terminal, plan=list, ask=help)
        mode_icon = ft.Icon(
            icon_name,
            size=14,
            color=icon_color,
            opacity=0.9,
        )

        # Main content: title only
        title_text = ft.Text(
            session.title or "",
            size=13,
            weight=ft.FontWeight.W_500 if is_selected else ft.FontWeight.NORMAL,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )

        item_content = ft.Row(
            controls=[mode_icon, title_text],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        if status_dot:
            item_content.controls.insert(0, status_dot)

        sid = session.id

        def on_item_hover(e) -> None:
            hovering = e.data == "true"
            # Use runtime selection state; do not overwrite selected style
            now_selected = self.state.current_session_id == sid
            if now_selected:
                inner.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
            else:
                inner.bgcolor = (
                    ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)
                    if hovering
                    else ft.Colors.TRANSPARENT
                )
            inner.update()

        # Flat design: single bgcolor, no border/ink to avoid layered overlay
        inner = ft.Container(
            content=item_content,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=8,
            bgcolor=(
                ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
                if is_selected
                else ft.Colors.TRANSPARENT
            ),
            on_click=lambda e, s=sid: self._handle_select(s),
            on_hover=on_item_hover,
            animate=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
            ink=False,
        )

        return ft.GestureDetector(
            content=inner,
            on_secondary_tap_down=lambda e, sid=session.id: self._show_context_menu(e, sid),
        )

    def _handle_select(self, session_id: str) -> None:
        _context_menu.dismiss()
        if self._on_select:
            self._on_select(session_id)

    def _handle_new_chat(self, e: ft.ControlEvent) -> None:
        _context_menu.dismiss()
        if self._on_new_chat:
            self._on_new_chat()

    def _handle_import(self, e: ft.ControlEvent) -> None:
        _context_menu.dismiss()
        if self._on_import:
            self._on_import()

    def _on_search(self, e: ft.ControlEvent) -> None:
        _context_menu.dismiss()
        self._search_query = (e.data or "").strip()
        # Debounce search to avoid rebuilding list on every keystroke
        if self._search_debounce_timer is not None:
            self._search_debounce_timer.cancel()
            self._search_debounce_timer = None
        try:
            loop = asyncio.get_event_loop()
            self._search_debounce_timer = loop.call_later(
                0.2, self._do_search_refresh,
            )
        except RuntimeError:
            self._do_search_refresh()

    def _do_search_refresh(self) -> None:
        """Execute the debounced search refresh."""
        self._search_debounce_timer = None
        self._refresh_list()
        if self._session_list:
            self._session_list.update()

    def _show_context_menu(self, e: ft.TapEvent, session_id: str) -> None:
        """Show context menu for session operations using floating menu."""
        if not e.page:
            return

        session = next(
            (s for s in self.state.sessions if s.id == session_id), None
        )
        if not session:
            return

        page = e.page

        def handle_action(action_fn, *args):
            def handler():
                # Dismiss menu first
                _context_menu.dismiss()
                # Then execute action
                if action_fn:
                    action_fn(*args)
            return handler

        # Build menu items
        items: list[ContextMenuItem] = [
            ContextMenuItem(
                icon=ft.Icons.EDIT,
                label=t("chat.rename"),
                on_click=handle_action(self._start_rename, session_id, page),
            ),
        ]

        if self._on_remove_from_list:
            items.append(ContextMenuItem(
                icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                label=t("chat.remove_from_list"),
                on_click=handle_action(self._on_remove_from_list, session_id),
            ))

        if self._on_delete:
            items.append(ContextMenuItem(
                icon=ft.Icons.DELETE,
                label=t("chat.delete"),
                on_click=handle_action(self._confirm_delete, session_id, page),
                icon_color=ft.Colors.ERROR,
            ))

        # Position menu at the right-click location (TapEvent.global_position)
        pos = e.global_position
        _context_menu.show(
            page,
            global_x=pos.x,
            global_y=pos.y,
            items=items,
        )

    def _confirm_delete(self, session_id: str, page: ft.Page) -> None:
        """Show a confirmation dialog before deleting a session."""
        from misaka.ui.common.theme import make_danger_button, make_dialog, make_text_button

        def do_delete(ev):
            page.pop_dialog()
            if self._on_delete:
                self._on_delete(session_id)

        dialog = make_dialog(
            title=t("chat.delete"),
            content=ft.Text(t("chat.confirm_delete")),
            actions=[
                make_text_button(t("common.cancel"), on_click=lambda ev: page.pop_dialog()),
                make_danger_button(t("common.delete"), on_click=do_delete),
            ],
        )
        page.show_dialog(dialog)

    def _start_rename(self, session_id: str, page: ft.Page) -> None:
        """Show a rename dialog for the session."""
        from misaka.ui.common.theme import (
            make_button,
            make_dialog,
            make_text_button,
            make_text_field,
        )

        session = next(
            (s for s in self.state.sessions if s.id == session_id), None
        )
        if not session:
            return

        rename_field = make_text_field(
            value=session.title,
            autofocus=True,
            dense=True,
        )

        def do_rename(ev):
            new_title = (rename_field.value or "").strip()
            if new_title and self._on_rename:
                self._on_rename(session_id, new_title)
            page.pop_dialog()

        dialog = make_dialog(
            title=t("chat.rename_session"),
            content=rename_field,
            actions=[
                make_text_button(
                    t("common.cancel"), on_click=lambda ev: page.pop_dialog(),
                ),
                make_button(t("chat.rename"), on_click=do_rename),
            ],
        )
        page.show_dialog(dialog)

    def refresh(self, clear_cache: bool = True) -> None:
        """Rebuild the session list from current state.

        Args:
            clear_cache: If True, clears the item cache before rebuilding.
                        Set to False for faster refresh when only updating selection.
        """
        if clear_cache:
            self._item_cache.clear()
        self._last_selected_id = self.state.current_session_id
        self._refresh_list()
        if self.state.background_streams and not self._pulse_timer_running:
            self._start_pulse_timer()
        if self._session_list:
            with contextlib.suppress(Exception):
                self._session_list.update()

    def refresh_selection(self) -> None:
        """Update only the selection highlight without rebuilding the list.

        Efficient for session switching — updates bgcolor on old and new
        selected items only.
        """
        new_id = self.state.current_session_id
        old_id = self._last_selected_id
        if new_id == old_id:
            return
        self._last_selected_id = new_id

        # Update old item (unselected)
        if old_id and old_id in self._item_cache:
            old_ctrl = self._item_cache[old_id]
            inner = getattr(old_ctrl, "content", None)
            if inner and isinstance(inner, ft.Container):
                inner.bgcolor = ft.Colors.TRANSPARENT

        # Update new item (selected)
        if new_id and new_id in self._item_cache:
            new_ctrl = self._item_cache[new_id]
            inner = getattr(new_ctrl, "content", None)
            if inner and isinstance(inner, ft.Container):
                inner.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)

        if self._session_list:
            with contextlib.suppress(Exception):
                self._session_list.update()

    def _update_dots_only(self) -> None:
        """Update only the opacity of existing status dots without rebuilding the list.

        This avoids recreating all controls (and their click handlers) on each
        pulse tick, which would swallow clicks from the user.
        """
        if not self._session_list:
            return
        target_opacity = 0.3 if self._pulse_phase else 1.0
        for control in self._session_list.controls:
            # Each item is GestureDetector > Container(inner) > Row(item_content)
            gesture = control
            inner = getattr(gesture, "content", None)
            if not inner:
                continue
            row = getattr(inner, "content", None)
            if not row or not hasattr(row, "controls") or not row.controls:
                continue
            first = row.controls[0]
            # Status dot is a small 6×6 Container with border_radius=3
            if (isinstance(first, ft.Container)
                    and getattr(first, "width", None) == 6
                    and getattr(first, "height", None) == 6):
                first.opacity = target_opacity

    def _start_pulse_timer(self) -> None:
        """Start a timer that toggles pulse phase for blinking dots."""
        if self._pulse_timer_running:
            return
        self._pulse_timer_running = True

        async def _pulse_loop() -> None:
            try:
                while self.state.background_streams:
                    self._pulse_phase = not self._pulse_phase
                    self._update_dots_only()
                    if self._session_list:
                        with contextlib.suppress(Exception):
                            self._session_list.update()
                    await asyncio.sleep(0.8)
            finally:
                self._pulse_timer_running = False
                self._pulse_phase = False

        self.state.page.run_task(_pulse_loop)
