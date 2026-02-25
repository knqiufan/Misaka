"""Chat list panel component.

Displays a scrollable list of chat sessions in the left sidebar
with search filtering, new-chat button, and context menu support.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.db.models import ChatSession
    from misaka.state import AppState


class ChatList(ft.Column):
    """Scrollable list of chat sessions with search and create."""

    def __init__(
        self,
        state: AppState,
        on_select: Callable[[str], None] | None = None,
        on_new_chat: Callable[[], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_rename: Callable[[str, str], None] | None = None,
        on_archive: Callable[[str], None] | None = None,
        on_import: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_select = on_select
        self._on_new_chat = on_new_chat
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_archive = on_archive
        self._on_import = on_import
        self._search_query = ""
        self._search_field: ft.TextField | None = None
        self._session_list: ft.ListView | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        from misaka.ui.theme import make_text_field as _mtf
        self._search_field = _mtf(
            hint_text=t("chat.search_sessions"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=8,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_change=self._on_search,
        )

        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        t("chat.chats"),
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        tooltip=t("chat.import_session"),
                        on_click=self._handle_import,
                        icon_size=18,
                        style=ft.ButtonStyle(padding=6),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        tooltip=t("chat.new_chat"),
                        on_click=self._handle_new_chat,
                        icon_size=20,
                        style=ft.ButtonStyle(padding=6),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=12, right=4, top=8, bottom=4),
        )

        search_bar = ft.Container(
            content=self._search_field,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        )

        self._session_list = ft.ListView(
            expand=True,
            spacing=2,
            padding=ft.Padding.symmetric(horizontal=4, vertical=4),
        )

        self.controls = [
            header,
            search_bar,
            ft.Divider(height=1),
            self._session_list,
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
                                size=32,
                                opacity=0.3,
                            ),
                            ft.Text(
                                msg,
                                italic=True,
                                size=12,
                                opacity=0.5,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=24,
                )
            ]
            return

        # Group sessions by date
        grouped = self._group_by_date(sessions)
        controls: list[ft.Control] = []
        for label, group in grouped:
            if label:
                controls.append(
                    ft.Container(
                        content=ft.Text(
                            label,
                            size=11,
                            weight=ft.FontWeight.W_600,
                            opacity=0.45,
                        ),
                        padding=ft.Padding.only(left=12, top=10, bottom=4),
                    )
                )
            for s in group:
                controls.append(self._build_session_item(s))

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

    def _get_filtered_sessions(self) -> list[ChatSession]:
        """Return sessions filtered by search query."""
        sessions = self.state.sessions
        if not self._search_query:
            return sessions
        q = self._search_query.lower()
        return [
            s for s in sessions
            if q in s.title.lower()
            or q in (s.project_name or "").lower()
        ]

    def _build_session_item(self, session: ChatSession) -> ft.Control:
        """Build a single session list item with hover-visible delete button."""
        is_selected = session.id == self.state.current_session_id

        subtitle_parts: list[str] = []
        if session.project_name:
            subtitle_parts.append(session.project_name)
        if session.updated_at:
            subtitle_parts.append(self._format_time(session.updated_at))
        subtitle = " \u00b7 ".join(subtitle_parts) if subtitle_parts else ""

        mode_colors = {
            "code": ft.Colors.BLUE,
            "plan": ft.Colors.ORANGE,
            "ask": ft.Colors.GREEN,
        }
        mode_color = mode_colors.get(session.mode, ft.Colors.GREY)

        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=16,
            icon_color=ft.Colors.ERROR,
            tooltip=t("chat.delete"),
            on_click=lambda e, sid=session.id: self._confirm_delete(sid, e.page),
            style=ft.ButtonStyle(padding=2),
            visible=False,
        )

        item_content = ft.Row(
            controls=[
                ft.Container(
                    width=3,
                    height=36,
                    border_radius=2,
                    bgcolor=ft.Colors.PRIMARY if is_selected else ft.Colors.TRANSPARENT,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            session.title,
                            size=13,
                            weight=ft.FontWeight.W_500 if is_selected else ft.FontWeight.NORMAL,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Text(
                                        session.mode.upper(),
                                        size=9,
                                        color=ft.Colors.WHITE,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    bgcolor=mode_color,
                                    border_radius=3,
                                    padding=ft.Padding.symmetric(horizontal=4, vertical=1),
                                ),
                                ft.Text(
                                    subtitle,
                                    size=11,
                                    opacity=0.45,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    expand=True,
                                ),
                            ],
                            spacing=6,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                delete_btn,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        def show_delete(e) -> None:
            delete_btn.visible = True
            delete_btn.update()

        def hide_delete(e) -> None:
            delete_btn.visible = False
            delete_btn.update()

        inner = ft.Container(
            content=item_content,
            padding=ft.Padding.only(left=4, right=4, top=5, bottom=5),
            border_radius=6,
            bgcolor=(
                ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)
                if is_selected
                else ft.Colors.TRANSPARENT
            ),
            on_click=lambda e, sid=session.id: self._handle_select(sid),
            on_long_press=lambda e, sid=session.id: self._show_context_menu(e, sid),
            ink=True,
        )

        return ft.GestureDetector(
            content=inner,
            on_enter=show_delete,
            on_exit=hide_delete,
        )

    def _handle_select(self, session_id: str) -> None:
        if self._on_select:
            self._on_select(session_id)

    def _handle_new_chat(self, e: ft.ControlEvent) -> None:
        if self._on_new_chat:
            self._on_new_chat()

    def _handle_import(self, e: ft.ControlEvent) -> None:
        if self._on_import:
            self._on_import()

    def _on_search(self, e: ft.ControlEvent) -> None:
        self._search_query = (e.data or "").strip()
        self._refresh_list()
        if self._session_list:
            self._session_list.update()

    def _show_context_menu(self, e: ft.ControlEvent, session_id: str) -> None:
        """Show context menu for session operations."""
        if not e.page:
            return

        session = next(
            (s for s in self.state.sessions if s.id == session_id), None
        )
        if not session:
            return

        page = e.page

        def close_menu(action_fn=None, *args):
            def handler(ev):
                page.pop_dialog()
                if action_fn:
                    action_fn(*args)
            return handler

        bottom_sheet = ft.BottomSheet(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            session.title,
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Divider(height=1),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.EDIT, size=20),
                            title=ft.Text(t("chat.rename"), size=13),
                            on_click=close_menu(self._start_rename, session_id, page),
                        ),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.ARCHIVE, size=20),
                            title=ft.Text(t("chat.archive"), size=13),
                            on_click=close_menu(self._on_archive, session_id) if self._on_archive else None,
                        ),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.DELETE, size=20, color=ft.Colors.ERROR),
                            title=ft.Text(t("chat.delete"), size=13, color=ft.Colors.ERROR),
                            on_click=close_menu(self._confirm_delete, session_id, page) if self._on_delete else None,
                        ),
                    ],
                    tight=True,
                    spacing=0,
                ),
                padding=16,
            ),
        )

        page.show_dialog(bottom_sheet)

    def _confirm_delete(self, session_id: str, page: ft.Page) -> None:
        """Show a confirmation dialog before deleting a session."""
        def do_delete(ev):
            page.pop_dialog()
            if self._on_delete:
                self._on_delete(session_id)

        dialog = ft.AlertDialog(
            title=ft.Text(t("chat.delete")),
            content=ft.Text(t("chat.confirm_delete")),
            actions=[
                ft.TextButton(t("common.cancel"), on_click=lambda ev: page.pop_dialog()),
                ft.Button(
                    t("common.delete"),
                    on_click=do_delete,
                    color=ft.Colors.WHITE,
                    bgcolor=ft.Colors.ERROR,
                ),
            ],
        )
        page.show_dialog(dialog)

    def _start_rename(self, session_id: str, page: ft.Page) -> None:
        """Show a rename dialog for the session."""
        session = next(
            (s for s in self.state.sessions if s.id == session_id), None
        )
        if not session:
            return

        rename_field = ft.TextField(
            value=session.title,
            autofocus=True,
            dense=True,
        )

        def do_rename(ev):
            new_title = (rename_field.value or "").strip()
            if new_title and self._on_rename:
                self._on_rename(session_id, new_title)
            page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text(t("chat.rename_session")),
            content=rename_field,
            actions=[
                ft.TextButton(t("common.cancel"), on_click=lambda ev: page.pop_dialog()),
                ft.Button(t("chat.rename"), on_click=do_rename),
            ],
        )
        page.show_dialog(dialog)

    def refresh(self) -> None:
        """Rebuild the session list from current state."""
        self._refresh_list()

    @staticmethod
    def _format_time(iso_str: str) -> str:
        """Format an ISO datetime to a relative or short time."""
        if not iso_str:
            return ""
        try:
            if "T" in iso_str:
                parts = iso_str.split("T")
                date_part = parts[0]
                time_part = parts[1][:5]
                from datetime import date
                today = date.today().isoformat()
                if date_part == today:
                    return time_part
                return date_part[5:]  # MM-DD
            return iso_str[:10]
        except (IndexError, ValueError):
            return ""
