"""Import session dialog component.

Dialog for browsing and importing Claude Code CLI sessions
from ~/.claude/projects/ into Misaka. Uses paginated loading
and on-demand metadata parsing for performance.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.services.session.session_import_service import (
    ClaudeSessionInfo,
    SessionImportService,
)
from misaka.ui.common.theme import (
    ERROR_RED,
    SUCCESS_GREEN,
    make_badge,
    make_button,
    make_danger_button,
    make_dialog,
    make_icon_button,
    make_text_button,
    make_text_field,
)
from misaka.utils.file_utils import format_file_size as _format_file_size
from misaka.utils.time_utils import format_relative_time as _format_relative_time

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)

PAGE_SIZE = 5
SEARCH_DEBOUNCE_MS = 350


class ImportSessionDialog:
    """Dialog for importing Claude CLI sessions with paginated loading."""

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
        self._loaded: list[ClaudeSessionInfo] = []
        self._total_count = 0
        self._offset = 0
        self._search_query = ""
        self._importing_id: str | None = None
        self._deleting_id: str | None = None
        self._loading = False
        self._search_debounce: asyncio.TimerHandle | None = None
        self._session_list: ft.ListView | None = None
        self._load_more_row: ft.Row | None = None
        self._status_text: ft.Text | None = None
        self._dialog: ft.AlertDialog | None = None
        self._build_dialog()
        self._schedule_load(offset=0, append=False)

    def open(self) -> None:
        self._loaded = []
        self._offset = 0
        self._total_count = 0
        self._schedule_load(offset=0, append=False)
        self._page.show_dialog(self._dialog)

    def close(self) -> None:
        self._page.pop_dialog()

    def _schedule_load(self, offset: int, append: bool) -> None:
        """Schedule async load; avoids blocking UI."""
        self._page.run_task(self._load_page_task, offset, append)

    async def _load_page_task(self, offset: int, append: bool) -> None:
        """Load a page of sessions asynchronously."""
        if self._loading:
            return
        self._loading = True
        self._set_loading_ui(True, is_search=bool(self._search_query.strip()))
        self._update_status_text()
        if self._session_list:
            self._session_list.update()
        self._update_load_more_visibility()
        self._refresh_footer()

        try:
            sessions, total = self._service.list_cli_sessions_paginated(
                limit=PAGE_SIZE,
                offset=offset,
                query=self._search_query.strip() or None,
            )
            if append:
                self._loaded.extend(sessions)
            else:
                self._loaded = sessions
            self._offset = offset + len(sessions)
            self._total_count = total
        except Exception:
            logger.exception("Failed to load CLI sessions")
            if not append:
                self._loaded = []
            self._total_count = 0
        finally:
            self._loading = False
            self._set_loading_ui(False)
            self._refresh_list()
            self._update_status_text()
            self._update_load_more_visibility()
            if self._session_list:
                self._session_list.update()
            self._refresh_footer()

    def _set_loading_ui(self, loading: bool, is_search: bool = False) -> None:
        """Update loading indicator in status area."""
        if self._status_text is None:
            return
        if loading:
            key = "searching" if is_search else "loading"
            self._status_text.value = t(f"import_session.{key}")
        else:
            self._status_text.value = ""

    def _update_status_text(self) -> None:
        """Update the status line (e.g. 'Showing 5 / 20')."""
        if self._status_text is None:
            return
        if self._loading:
            return
        if self._total_count == 0 and not self._loaded:
            self._status_text.value = ""
            return
        shown = len(self._loaded)
        total = self._total_count
        self._status_text.value = t(
            "import_session.showing_count",
            shown=shown,
            total=total,
        )

    def _update_load_more_visibility(self) -> None:
        """Show/hide load more button based on whether more items exist."""
        if self._load_more_row is None:
            return
        has_more = len(self._loaded) < self._total_count
        self._load_more_row.visible = has_more and not self._loading

    def _refresh_footer(self) -> None:
        """Refresh footer controls after status/visibility changes."""
        if self._status_text:
            self._status_text.update()
        if self._load_more_row:
            self._load_more_row.update()

    def _build_dialog(self) -> None:
        """Build the dialog UI with search, list, load more, and status."""
        search_field = make_text_field(
            hint_text=t("import_session.search"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_change=self._on_search_changed,
            expand=True,
            margin=ft.Margin.only(left=4, right=4, top=4, bottom=10),
        )
        search_bar = ft.Row(controls=[search_field])

        self._session_list = ft.ListView(
            expand=True,
            spacing=10,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
            height=400,
        )

        self._status_text = ft.Text(
            "",
            size=11,
            opacity=0.5,
        )

        load_more_btn = make_text_button(
            t("import_session.load_more"),
            icon=ft.Icons.EXPAND_MORE_ROUNDED,
            on_click=self._on_load_more,
        )
        self._load_more_row = ft.Row(
            controls=[
                ft.Container(expand=True),
                load_more_btn,
                ft.Container(expand=True),
            ],
            visible=False,
        )

        content = ft.Container(
            content=ft.Column(
                controls=[
                    search_bar,
                    # ft.Divider(height=1),
                    self._session_list,
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                self._status_text,
                                self._load_more_row,
                            ],
                            spacing=8,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.only(top=8, bottom=4),
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            width=520,
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
        """Rebuild the session list from loaded data."""
        if self._session_list is None:
            return

        if not self._loaded:
            self._session_list.controls = [
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(
                                ft.Icons.FOLDER_OPEN,
                                size=40,
                                opacity=0.25,
                            ),
                            ft.Text(
                                t("import_session.no_sessions"),
                                italic=True,
                                size=13,
                                opacity=0.5,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=32,
                )
            ]
            return

        self._session_list.controls = [
            self._build_session_card(s) for s in self._loaded
        ]

    def _build_session_card(self, session: ClaudeSessionInfo) -> ft.Control:
        """Build a single session card with compact layout."""
        is_importing = self._importing_id == session.session_id
        is_deleting = self._deleting_id == session.session_id

        title_row = self._build_title_row(session)
        preview_row = self._build_preview_row(session)
        meta_row = self._build_meta_row(session)
        action_ctrl = self._build_action_row(
            session,
            is_importing,
            is_deleting,
        )

        card = ft.Container(
            content=ft.Column(
                controls=[title_row, preview_row, meta_row, action_ctrl],
                spacing=6,
                tight=True,
            ),
            padding=14,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
        )
        return card

    def _build_title_row(self, session: ClaudeSessionInfo) -> ft.Control:
        """Build title row with project name and optional git badge."""
        title_controls: list[ft.Control] = [
            ft.Text(
                session.project_name or "Untitled",
                size=13,
                weight=ft.FontWeight.W_600,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
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
        return ft.Row(
            controls=title_controls,
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_preview_row(self, session: ClaudeSessionInfo) -> ft.Control:
        """Build preview text row."""
        preview = (session.preview or "").strip()
        if not preview:
            return ft.Container(height=0)
        text = preview[:100] + ("..." if len(preview) > 100 else "")
        return ft.Text(
            text,
            size=11,
            opacity=0.65,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

    def _build_meta_row(self, session: ClaudeSessionInfo) -> ft.Control:
        """Build metadata row (messages, time, size)."""
        msg_count = session.user_message_count + session.assistant_message_count
        parts: list[str] = []
        if msg_count > 0:
            parts.append(t("import_session.messages", count=msg_count))
        if session.updated_at:
            parts.append(_format_relative_time(session.updated_at))
        if session.file_size > 0:
            parts.append(_format_file_size(session.file_size))
        if not parts:
            return ft.Container(height=0)
        return ft.Text(
            " \u00b7 ".join(parts),
            size=10,
            opacity=0.45,
        )

    def _build_busy_action(
        self,
        text_key: str,
    ) -> ft.Control:
        """Build a compact busy indicator row for import/delete actions."""
        return ft.Row(
            controls=[
                ft.ProgressRing(width=14, height=14, stroke_width=2),
                ft.Text(
                    t(f"import_session.{text_key}"),
                    size=11,
                    opacity=0.7,
                ),
            ],
            spacing=6,
            tight=True,
        )

    def _build_primary_action_control(
        self,
        session: ClaudeSessionInfo,
        is_importing: bool,
        is_deleting: bool,
    ) -> ft.Control:
        """Build the main action control for a CLI session row."""
        if is_importing:
            return self._build_busy_action("importing")
        if is_deleting:
            return self._build_busy_action("deleting")
        if self._is_already_imported(session.session_id):
            return ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=SUCCESS_GREEN),
                    ft.Text(
                        t("import_session.already_imported"),
                        size=11,
                        color=SUCCESS_GREEN,
                    ),
                ],
                spacing=4,
                tight=True,
            )
        return make_button(
            t("import_session.import_btn"),
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda e, sid=session.session_id: self._handle_import(sid),
        )

    def _build_delete_button(
        self,
        session_id: str,
        disabled: bool,
    ) -> ft.Control:
        """Build the delete icon button shown on each session row."""
        return make_icon_button(
            ft.Icons.DELETE_OUTLINE,
            tooltip=t("common.delete"),
            icon_color=ERROR_RED,
            icon_size=18,
            disabled=disabled,
            on_click=lambda e, sid=session_id: self._confirm_delete_cli_session(sid),
        )

    def _build_action_row(
        self,
        session: ClaudeSessionInfo,
        is_importing: bool,
        is_deleting: bool,
    ) -> ft.Control:
        """Build the row containing import state/button and delete icon."""
        primary = self._build_primary_action_control(
            session,
            is_importing,
            is_deleting,
        )
        if is_importing or is_deleting:
            return primary
        delete_btn = self._build_delete_button(
            session.session_id,
            disabled=False,
        )
        return ft.Row(
            controls=[
                primary,
                ft.Container(expand=True),
                delete_btn,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _is_already_imported(self, session_id: str) -> bool:
        """Check if session was already imported."""
        db = None
        if hasattr(self._state, "services") and self._state.services:
            db = self._state.services.db
        if db:
            return self._get_existing_imported_session(db, session_id) is not None
        return any(s.sdk_session_id == session_id for s in self._state.sessions)

    @staticmethod
    def _get_existing_imported_session(db, session_id: str):
        """Return a completed imported session, ignoring stale empty imports."""
        existing = db.get_session_by_sdk_id(session_id)
        if existing is None:
            return None
        messages, _ = db.get_messages(existing.id, limit=1)
        if not messages:
            return None
        return existing

    def _sync_imported_session_state(self, session_id: str, session) -> None:
        """Merge the imported session into in-memory state without duplicates."""
        remaining = [
            s
            for s in self._state.sessions
            if s.id != session.id and s.sdk_session_id != session_id
        ]
        self._state.sessions = [session] + remaining

    def _reset_importing_ui(self) -> None:
        """Clear importing state and refresh the visible list."""
        self._importing_id = None
        self._refresh_list()
        if self._session_list:
            self._session_list.update()

    def _reset_deleting_ui(self) -> None:
        """Clear deleting state and refresh the visible list."""
        self._deleting_id = None
        self._refresh_list()
        if self._session_list:
            self._session_list.update()

    def _notify_import_success(self) -> None:
        """Show the standard import success feedback."""
        self._page.show_dialog(
            ft.SnackBar(
                content=ft.Text(t("import_session.import_success")),
                bgcolor=ft.Colors.GREEN,
            )
        )

    def _notify_import_error(self, error: Exception) -> None:
        """Show the standard import failure feedback."""
        self._page.show_dialog(
            ft.SnackBar(
                content=ft.Text(
                    t("import_session.import_error", error=str(error))
                ),
                bgcolor=ft.Colors.ERROR,
            )
        )

    def _notify_delete_success(self) -> None:
        """Show the standard delete success feedback."""
        self._page.show_dialog(
            ft.SnackBar(
                content=ft.Text(t("import_session.delete_success")),
                bgcolor=ft.Colors.GREEN,
            )
        )

    def _notify_delete_error(self, error: Exception) -> None:
        """Show the standard delete failure feedback."""
        self._page.show_dialog(
            ft.SnackBar(
                content=ft.Text(
                    t("import_session.delete_error", error=str(error))
                ),
                bgcolor=ft.Colors.ERROR,
            )
        )

    def _reload_after_delete(self) -> None:
        """Reload the current import list after deleting a CLI session."""
        self._deleting_id = None
        self._loaded = []
        self._offset = 0
        self._total_count = 0
        self._refresh_list()
        if self._session_list:
            self._session_list.update()
        self._update_status_text()
        self._update_load_more_visibility()
        self._refresh_footer()
        self._schedule_load(offset=0, append=False)

    def _confirm_delete_cli_session(self, session_id: str) -> None:
        """Show a confirmation dialog before deleting a CLI session."""
        if self._importing_id or self._deleting_id:
            return

        def do_delete(e: ft.ControlEvent) -> None:
            self._page.pop_dialog()
            self._handle_delete_cli_session(session_id)

        dialog = make_dialog(
            title=t("chat.delete"),
            content=ft.Text(t("chat.confirm_delete")),
            actions=[
                make_text_button(
                    t("common.cancel"),
                    on_click=lambda e: self._page.pop_dialog(),
                ),
                make_danger_button(t("common.delete"), on_click=do_delete),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dialog)

    def _handle_delete_cli_session(self, session_id: str) -> None:
        """Delete the selected CLI session and refresh the dialog list."""
        if self._importing_id or self._deleting_id:
            return
        self._deleting_id = session_id
        self._refresh_list()
        if self._session_list:
            self._session_list.update()
        try:
            self._service.delete_cli_session(session_id)
        except Exception as exc:
            logger.exception("Failed to delete CLI session %s", session_id)
            self._reset_deleting_ui()
            self._notify_delete_error(exc)
            return
        self._reload_after_delete()
        self._notify_delete_success()

    def _complete_import(self, session_id: str, session) -> None:
        """Finalize a successful import and refresh the page state."""
        self._sync_imported_session_state(session_id, session)
        self._importing_id = None
        try:
            self.close()
            self._state.update()
            self._notify_import_success()
            self._on_import(session.id)
        except Exception:
            logger.exception(
                "Imported session %s, but failed to refresh UI",
                session_id,
            )
            self._state.update()

    def _on_search_changed(self, e: ft.ControlEvent) -> None:
        """Handle search input with debounce."""
        self._search_query = (e.data or "").strip()
        if self._search_debounce:
            self._search_debounce.cancel()
            self._search_debounce = None
        try:
            loop = asyncio.get_event_loop()
            self._search_debounce = loop.call_later(
                SEARCH_DEBOUNCE_MS / 1000.0,
                self._do_search,
            )
        except RuntimeError:
            self._do_search()

    def _do_search(self) -> None:
        """Execute debounced search."""
        self._search_debounce = None
        self._loaded = []
        self._offset = 0
        self._total_count = 0
        self._schedule_load(offset=0, append=False)

    def _on_load_more(self, e: ft.ControlEvent) -> None:
        """Load next page of sessions."""
        self._schedule_load(offset=self._offset, append=True)

    def _handle_import(self, session_id: str) -> None:
        """Import the selected session."""
        self._importing_id = session_id
        self._refresh_list()
        if self._session_list:
            self._session_list.update()

        db = None
        if hasattr(self._state, "services") and self._state.services:
            db = self._state.services.db

        if not db:
            self._reset_importing_ui()
            return

        try:
            session = self._service.import_session(session_id, db)
        except Exception as exc:
            existing = self._get_existing_imported_session(db, session_id)
            if existing is not None:
                self._complete_import(session_id, existing)
                return
            logger.exception("Failed to import session %s", session_id)
            self._reset_importing_ui()
            self._notify_import_error(exc)
            return

        self._complete_import(session_id, session)
