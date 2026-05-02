"""Document list table component."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_icon_button

if TYPE_CHECKING:
    from misaka.db.models import KBDocument

_STATUS_COLORS = {
    "pending": ft.Colors.GREY,
    "parsing": ft.Colors.AMBER,
    "embedding": ft.Colors.BLUE,
    "ready": ft.Colors.GREEN,
    "error": ft.Colors.ERROR,
}

_STATUS_ICONS = {
    "pending": ft.Icons.HOURGLASS_EMPTY,
    "parsing": ft.Icons.AUTORENEW,
    "embedding": ft.Icons.MEMORY,
    "ready": ft.Icons.CHECK_CIRCLE_OUTLINE,
    "error": ft.Icons.ERROR_OUTLINE,
}

_TYPE_ICONS = {
    "txt": ft.Icons.TEXT_SNIPPET_OUTLINED,
    "markdown": ft.Icons.ARTICLE_OUTLINED,
    "docx": ft.Icons.DESCRIPTION_OUTLINED,
    "xlsx": ft.Icons.TABLE_CHART_OUTLINED,
    "pdf": ft.Icons.PICTURE_AS_PDF_OUTLINED,
}


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _status_label(status: str) -> str:
    return t(f"kb.doc_status_{status}")


def build_document_table(
    docs: list[KBDocument],
    *,
    on_view: Callable[[str], None] | None = None,
    on_reprocess: Callable[[str], None] | None = None,
    on_delete: Callable[[str], None] | None = None,
) -> ft.Container:
    """Build a tabular document list."""
    header = _build_header_row()
    rows = [_build_doc_row(doc, on_view, on_reprocess, on_delete) for doc in docs]

    return ft.Container(
        content=ft.Column(
            controls=[header, *rows],
            spacing=0,
            tight=True,
        ),
        padding=ft.Padding(left=24, right=24, top=0, bottom=16),
    )


def _build_header_row() -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(t("kb.name"), size=10, opacity=0.4, weight=ft.FontWeight.W_600, expand=3),
                ft.Text(t("kb.doc_type"), size=10, opacity=0.4, weight=ft.FontWeight.W_600, expand=1),
                ft.Text(t("kb.doc_size"), size=10, opacity=0.4, weight=ft.FontWeight.W_600, expand=1),
                ft.Text(t("kb.doc_chunks"), size=10, opacity=0.4, weight=ft.FontWeight.W_600, expand=1),
                ft.Text(t("kb.doc_status"), size=10, opacity=0.4, weight=ft.FontWeight.W_600, expand=1),
                ft.Container(width=100),
            ],
            spacing=8,
        ),
        padding=ft.Padding(left=8, right=8, top=6, bottom=6),
        border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE))),
    )


def _build_doc_row(
    doc: KBDocument,
    on_view: Callable[[str], None] | None,
    on_reprocess: Callable[[str], None] | None,
    on_delete: Callable[[str], None] | None,
) -> ft.Container:
    status_color = _STATUS_COLORS.get(doc.status, ft.Colors.GREY)
    status_icon = _STATUS_ICONS.get(doc.status, ft.Icons.HELP_OUTLINE)
    type_icon = _TYPE_ICONS.get(doc.file_type, ft.Icons.INSERT_DRIVE_FILE_OUTLINED)

    actions = ft.Row(
        controls=[
            make_icon_button(
                ft.Icons.VISIBILITY_OUTLINED,
                tooltip=t("kb.doc_view"),
                on_click=lambda _, did=doc.id: on_view(did) if on_view else None,
                size=15,
            ),
            make_icon_button(
                ft.Icons.REFRESH,
                tooltip=t("kb.doc_reprocess"),
                on_click=lambda _, did=doc.id: on_reprocess(did) if on_reprocess else None,
                size=15,
            ),
            make_icon_button(
                ft.Icons.DELETE_OUTLINE,
                tooltip=t("kb.doc_delete"),
                on_click=lambda _, did=doc.id: on_delete(did) if on_delete else None,
                size=15,
            ),
        ],
        spacing=0,
        tight=True,
    )

    error_tooltip = doc.error_message if doc.status == "error" and doc.error_message else None

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(type_icon, size=14, opacity=0.4),
                        ft.Text(
                            doc.file_name,
                            size=12,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=6,
                    expand=3,
                    tight=True,
                ),
                ft.Text(doc.file_type.upper(), size=11, opacity=0.5, expand=1),
                ft.Text(_format_size(doc.file_size), size=11, opacity=0.5, expand=1),
                ft.Text(str(doc.chunk_count), size=11, opacity=0.5, expand=1),
                ft.Row(
                    controls=[
                        ft.Icon(status_icon, size=13, color=status_color),
                        ft.Text(
                            _status_label(doc.status),
                            size=11,
                            color=status_color,
                            tooltip=error_tooltip,
                        ),
                    ],
                    spacing=4,
                    tight=True,
                    expand=1,
                ),
                actions,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(left=8, right=8, top=8, bottom=8),
        border=ft.Border(
            bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE)),
        ),
        on_hover=lambda e: _on_row_hover(e),
    )


def _on_row_hover(e: ft.ControlEvent) -> None:
    ctrl = e.control
    if isinstance(ctrl, ft.Container):
        ctrl.bgcolor = (
            ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE)
            if e.data == "true"
            else None
        )
        ctrl.update()
