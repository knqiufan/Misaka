"""Import session dialog component.

Dialog for browsing and importing Claude Code CLI sessions
from ~/.claude/projects/ into Misaka.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t
from misaka.services.session.session_import_service import (
    ClaudeSessionInfo,
    SessionImportService,
)
from misaka.ui.common.theme import (
    SUCCESS_GREEN,
    make_badge,
    make_button,
    make_dialog,
    make_divider,
    make_text_button,
    make_text_field,
)
from misaka.utils.file_utils import format_file_size as _format_file_size
from misaka.utils.time_utils import format_relative_time as _format_relative_time

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)


class ImportSessionDialog:
    """Dialog for importing Claude CLI sessions."""

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        on_import: Callable[[str], None],
    ) -> None:
        self._page = page
        self._state = state
        self._on_import = on_import
        self._service = SessionImportService()
        self._sessions: list[ClaudeSessionInfo] = []
        self._filtered: list[ClaudeSessionInfo] = []
        self._search_query = ""
        self._importing_id: str | None = None
        self._session_list: ft.ListView | None = None
        self._dialog: ft.AlertDialog | None = None
        self._load_sessions()
        self._build_dialog()

    def open(self) -> None:
        self._load_sessions()
        self._refresh_list()
        self._page.show_dialog(self._dialog)

    def close(self) -> None:
        self._page.pop_dialog()

    def _load_sessions(self) -> None:
        try:
            self._sessions = self._service.list_cli_sessions()
        except Exception:
            logger.exception("Failed to load CLI sessions")
            self._sessions = []
        self._apply_filter()

    def _apply_filter(self) -> None:
        if not self._search_query:
            self._filtered = list(self._sessions)
            return
        q = self._search_query.lower()
        self._filtered = [
            s for s in self._sessions
            if q in (s.project_name or "").lower()
            or q in (s.preview or "").lower()
            or q in (s.cwd or "").lower()
            or q in (s.git_branch or "").lower()
        ]

    def _build_dialog(self) -> None:
        search_field = make_text_field(
            hint_text=t("import_session.search"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_change=self._on_search_changed,
        )

        self._session_list = ft.ListView(
            expand=True,
            spacing=4,
            padding=ft.Padding.symmetric(horizontal=4, vertical=4),
            height=400,
        )
        self._refresh_list()

        content = ft.Container(
            content=ft.Column(
                controls=[search_field, make_divider(), self._session_list],
                spacing=8,
                tight=True,
            ),
            width=480,
        )

        self._dialog = make_dialog(
            title=t("import_session.title"),
            content=content,
            actions=[
                make_text_button(t("common.cancel"), on_click=lambda e: self.close()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _refresh_list(self) -> None:
        if self._session_list is None:
            return

        if not self._filtered:
            self._session_list.controls = [
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.FOLDER_OPEN, size=32, opacity=0.3),
                            ft.Text(
                                t("import_session.no_sessions"),
                                italic=True, size=12, opacity=0.5,
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

        self._session_list.controls = [
            self._build_session_item(s) for s in self._filtered
        ]

    def _build_session_item(self, session: ClaudeSessionInfo) -> ft.Control:
        is_importing = self._importing_id == session.session_id

        # Title + git branch badge
        title_controls: list[ft.Control] = [
            ft.Text(
                session.project_name or "Untitled",
                size=13, weight=ft.FontWeight.BOLD,
                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                expand=True,
            ),
        ]
        if session.git_branch:
            title_controls.append(
                make_badge(
                    session.git_branch,
                    bgcolor="#64748b",
                    size=10,
                )
            )

        title_row = ft.Row(
            controls=title_controls, spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Preview
        preview_text = (session.preview or "")[:120]
        if len(session.preview or "") > 120:
            preview_text += "..."
        preview = ft.Text(preview_text, size=11, opacity=0.6, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)

        # Metadata: message count, relative time, file size
        msg_count = session.user_message_count + session.assistant_message_count
        detail_parts: list[str] = []
        if msg_count > 0:
            detail_parts.append(t("import_session.messages", count=msg_count))
        if session.updated_at:
            detail_parts.append(_format_relative_time(session.updated_at))
        if session.file_size > 0:
            detail_parts.append(_format_file_size(session.file_size))

        meta_row = ft.Text(
            " \u00b7 ".join(detail_parts),
            size=10, opacity=0.4,
        ) if detail_parts else ft.Container(height=0)

        # CWD
        cwd_row = ft.Container(height=0)
        if session.cwd:
            cwd_display = session.cwd
            parts = cwd_display.replace("\\", "/").rstrip("/").rsplit("/", 2)
            if len(parts) > 2:
                cwd_display = ".../" + "/".join(parts[-2:])
            cwd_row = ft.Row(
                controls=[
                    ft.Icon(ft.Icons.FOLDER_OUTLINED, size=12, opacity=0.5),
                    ft.Text(cwd_display, size=10, opacity=0.5, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=2, tight=True,
            )

        # Import button / loading / already imported
        if is_importing:
            action = ft.Row(
                controls=[
                    ft.ProgressRing(width=14, height=14, stroke_width=2),
                    ft.Text(t("import_session.importing"), size=11, opacity=0.7),
                ],
                spacing=6, tight=True,
            )
        elif self._is_already_imported(session.session_id):
            action = make_badge(
                t("import_session.already_imported"),
                bgcolor=SUCCESS_GREEN,
            )
        else:
            action = make_button(
                t("import_session.import_btn"),
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e, sid=session.session_id: self._handle_import(sid),
            )

        card = ft.Column(
            controls=[title_row, preview, cwd_row, meta_row, ft.Container(content=action, alignment=ft.Alignment.CENTER_RIGHT)],
            spacing=4, tight=True,
        )

        return ft.Container(
            content=card, padding=12, border_radius=12,
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            ink=True,
        )

    def _is_already_imported(self, session_id: str) -> bool:
        for s in self._state.sessions:
            if s.sdk_session_id == session_id:
                return True
        return False

    def _on_search_changed(self, e: ft.ControlEvent) -> None:
        self._search_query = (e.data or "").strip()
        self._apply_filter()
        self._refresh_list()
        if self._session_list:
            self._session_list.update()

    def _handle_import(self, session_id: str) -> None:
        self._importing_id = session_id
        self._refresh_list()
        self._page.update()

        db = None
        if hasattr(self._state, "services") and self._state.services:
            db = self._state.services.db

        if not db:
            self._importing_id = None
            self._refresh_list()
            self._page.update()
            return

        try:
            session = self._service.import_session(session_id, db)

            # Add to state
            self._state.sessions = [session] + self._state.sessions

            self.close()
            self._importing_id = None

            self._page.show_dialog(
                ft.SnackBar(content=ft.Text(t("import_session.import_success")), bgcolor=ft.Colors.GREEN)
            )

            self._on_import(session.id)

        except Exception as exc:
            logger.exception("Failed to import session %s", session_id)
            self._importing_id = None
            self._refresh_list()
            self._page.update()

            self._page.show_dialog(
                ft.SnackBar(content=ft.Text(t("import_session.import_error", error=str(exc))), bgcolor=ft.Colors.ERROR)
            )
