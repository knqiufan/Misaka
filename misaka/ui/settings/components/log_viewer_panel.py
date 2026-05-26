"""Runtime log viewer panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    ERROR_RED,
    MONO_FONT_FAMILY,
    RADIUS_LG,
    WARNING_AMBER,
    make_outlined_button,
    show_snackbar,
)
from misaka.utils.log_buffer import get_ring_handler

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_LOG_LEVELS = ("All", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _log_level_color(level: str) -> str:
    if level in ("ERROR", "CRITICAL"):
        return ERROR_RED
    if level == "WARNING":
        return WARNING_AMBER
    if level == "DEBUG":
        return ft.Colors.ON_SURFACE_VARIANT
    return ft.Colors.ON_SURFACE


def _log_level_bg(level: str) -> str:
    if level in ("ERROR", "CRITICAL"):
        return ft.Colors.with_opacity(0.12, ERROR_RED)
    if level == "WARNING":
        return ft.Colors.with_opacity(0.12, WARNING_AMBER)
    if level == "DEBUG":
        return ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)
    return ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)


class LogViewerPanel(ft.Container):
    """Panel displaying runtime log entries with level filtering."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)
        self._log_level_filter: str = "All"
        self._build_ui()

    def refresh(self) -> None:
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        handler = get_ring_handler()
        level_filter = None if self._log_level_filter == "All" else self._log_level_filter
        entries = handler.get_entries(level_filter=level_filter)

        level_chips = self._build_level_chips()
        count_text = t("settings.log_viewer_entries").format(count=len(entries))
        log_container = self._build_log_container(entries)

        self.content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            t("settings.log_viewer"),
                            size=16,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(count_text, size=11, opacity=0.5),
                        ft.Container(expand=True),
                        make_outlined_button(
                            t("settings.log_viewer_copy"),
                            icon=ft.Icons.COPY,
                            on_click=self._handle_copy,
                        ),
                        make_outlined_button(
                            t("settings.log_viewer_clear"),
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=self._handle_clear,
                        ),
                        make_outlined_button(
                            t("settings.log_viewer_refresh"),
                            icon=ft.Icons.REFRESH,
                            on_click=self._handle_refresh,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                ft.Text(t("settings.log_viewer_desc"), size=12, opacity=0.6),
                ft.Row(controls=level_chips, spacing=6, wrap=True),
                log_container,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _build_level_chips(self) -> list[ft.Control]:
        chips: list[ft.Control] = []
        for lvl in _LOG_LEVELS:
            label = t("settings.log_viewer_all") if lvl == "All" else lvl
            is_selected = self._log_level_filter == lvl
            chips.append(
                ft.Container(
                    content=ft.Text(
                        label,
                        size=11,
                        weight=(
                            ft.FontWeight.W_600 if is_selected
                            else ft.FontWeight.W_400
                        ),
                        color=(
                            ft.Colors.ON_PRIMARY if is_selected
                            else ft.Colors.ON_SURFACE_VARIANT
                        ),
                    ),
                    bgcolor=(
                        ft.Colors.PRIMARY if is_selected
                        else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)
                    ),
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    on_click=lambda e, lv=lvl: self._set_level_filter(lv),
                    ink=True,
                ),
            )
        return chips

    def _build_log_container(self, entries) -> ft.Control:
        if entries:
            log_rows: list[ft.Control] = []
            for i, entry in enumerate(entries):
                log_rows.append(self._build_entry_row(entry, i))
            log_content: ft.Control = ft.ListView(
                controls=log_rows,
                spacing=2,
                padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                auto_scroll=True,
            )
        else:
            log_content = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.ARTICLE_OUTLINED, size=32, opacity=0.15),
                        ft.Text(
                            t("settings.log_viewer_empty"),
                            size=12,
                            italic=True,
                            opacity=0.4,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                ),
                expand=True,
                alignment=ft.Alignment.CENTER,
            )

        return ft.Container(
            content=log_content,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            border_radius=RADIUS_LG,
            height=320,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    @staticmethod
    def _build_entry_row(entry, index: int) -> ft.Control:
        level = entry.level
        level_color = _log_level_color(level)
        level_bg = _log_level_bg(level)

        level_badge = ft.Container(
            content=ft.Text(
                level[:4],
                size=9,
                weight=ft.FontWeight.W_700,
                color=level_color,
                font_family=MONO_FONT_FAMILY,
            ),
            bgcolor=level_bg,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=5, vertical=1),
            width=42,
            alignment=ft.Alignment.CENTER,
        )

        timestamp_text = ft.Text(
            entry.timestamp,
            size=10,
            font_family=MONO_FONT_FAMILY,
            opacity=0.45,
            no_wrap=True,
        )

        logger_text = ft.Text(
            entry.logger_name,
            size=10,
            font_family=MONO_FONT_FAMILY,
            opacity=0.5,
            color=ft.Colors.PRIMARY,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        msg_text = ft.Text(
            entry.message,
            size=11,
            font_family=MONO_FONT_FAMILY,
            selectable=True,
            max_lines=3,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        row_bg = (
            ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE)
            if index % 2 == 0
            else None
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    level_badge,
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[timestamp_text, logger_text],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            msg_text,
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
            border_radius=6,
            bgcolor=row_bg,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _set_level_filter(self, level: str) -> None:
        self._log_level_filter = level
        self._build_ui()
        self.state.update()

    def _handle_refresh(self, e: ft.ControlEvent) -> None:
        self._build_ui()
        self.state.update()

    def _handle_clear(self, e: ft.ControlEvent) -> None:
        handler = get_ring_handler()
        handler.clear()
        self._build_ui()
        self.state.update()
        page = e.page
        if page:
            show_snackbar(page, t("settings.log_viewer_cleared"))

    async def _handle_copy(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return
        handler = get_ring_handler()
        level_filter = (
            None if self._log_level_filter == "All" else self._log_level_filter
        )
        entries = handler.get_entries(level_filter=level_filter)
        text = "\n".join(entry.format_line() for entry in entries)
        await ft.Clipboard().set(text)
        show_snackbar(page, t("settings.log_viewer_copied"))
