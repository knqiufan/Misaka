"""Import session dialog component.

Dialog for browsing and importing Claude Code CLI sessions
from ~/.claude/projects/ into Misaka.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t
from misaka.services.session_import_service import (
    SessionImportService,
    ClaudeSessionInfo,
)

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_relative_time(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return iso_str[:10]
        if total_seconds < 60:
            return f"{total_seconds}s ago"
        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        if months < 12:
            return f"{months}mo ago"
        return f"{days // 365}y ago"
    except (ValueError, TypeError, AttributeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


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
        search_field = ft.TextField(
            hint_text=t("import_session.search"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=8,
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
                controls=[search_field, ft.Divider(height=1), self._session_list],
                spacing=8,
                tight=True,
            ),
            width=480,
        )

        self._dialog = ft.AlertDialog(
            title=ft.Text(t("import_session.title"), size=18, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton(t("common.cancel"), on_click=lambda e: self.close()),
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
                ft.Container(
                    content=ft.Text(
                        session.git_branch, size=10,
                        color=ft.Colors.WHITE, weight=ft.FontWeight.W_500,
                    ),
                    bgcolor=ft.Colors.BLUE_GREY,
                    border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=1),
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
            action = ft.Container(
                content=ft.Text(
                    t("import_session.already_imported"),
                    size=10, color=ft.Colors.GREEN, weight=ft.FontWeight.W_500,
                ),
                border=ft.Border.all(1, ft.Colors.GREEN),
                border_radius=4,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            )
        else:
            action = ft.Button(
                content=t("import_session.import_btn"),
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e, sid=session.session_id: self._handle_import(sid),
            )

        card = ft.Column(
            controls=[title_row, preview, cwd_row, meta_row, ft.Container(content=action, alignment=ft.Alignment.CENTER_RIGHT)],
            spacing=4, tight=True,
        )

        return ft.Container(
            content=card, padding=10, border_radius=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), ink=True,
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
            self._state.sessions.insert(0, session)

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
