"""Knowledge base card component for the list view."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_icon_button

if TYPE_CHECKING:
    from misaka.db.models import KnowledgeBase

_STATUS_COLORS = {
    "active": ft.Colors.GREEN,
    "building": ft.Colors.AMBER,
    "error": ft.Colors.ERROR,
}


def _status_label(status: str) -> str:
    key = f"kb.status_{status}"
    return t(key)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_kb_card(
    kb: KnowledgeBase,
    *,
    warning: str | None = None,
    on_manage: Callable | None = None,
    on_edit: Callable | None = None,
    on_delete: Callable | None = None,
) -> ft.Container:
    """Build a knowledge base info card."""
    status_color = _STATUS_COLORS.get(kb.status, ft.Colors.GREY)
    status_text = _status_label(kb.status)

    stat_row = ft.Row(
        controls=[
            _stat_chip(ft.Icons.DESCRIPTION_OUTLINED, f"{kb.document_count}", t("kb.documents")),
            _stat_chip(ft.Icons.GRID_VIEW, f"{kb.chunk_count}", t("kb.chunks")),
        ],
        spacing=12,
    )

    model_text = kb.embedding_model_id or "—"
    if len(model_text) > 28:
        model_text = model_text[:26] + "…"

    action_row = ft.Row(
        controls=[
            ft.TextButton(
                t("kb.manage"),
                icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                on_click=on_manage,
                style=ft.ButtonStyle(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                ),
            ),
            ft.Container(expand=True),
            make_icon_button(
                ft.Icons.EDIT_OUTLINED,
                tooltip=t("kb.edit"),
                on_click=on_edit,
                size=16,
            ),
            make_icon_button(
                ft.Icons.DELETE_OUTLINE,
                tooltip=t("kb.delete"),
                on_click=on_delete,
                size=16,
            ),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            kb.name,
                            size=14,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Container(
                            content=ft.Text(status_text, size=10, color=status_color),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                            border_radius=10,
                            bgcolor=ft.Colors.with_opacity(0.1, status_color),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    kb.description or "—",
                    size=11,
                    opacity=0.55,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                *(_build_warning_row(warning) if warning else []),
                ft.Text(
                    f"📐 {model_text}",
                    size=10,
                    opacity=0.4,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                stat_row,
                ft.Divider(height=1, color=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
                action_row,
            ],
            spacing=6,
            tight=True,
        ),
        padding=14,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
        shadow=ft.BoxShadow(
            blur_radius=6,
            spread_radius=-2,
            color=ft.Colors.with_opacity(0.03, ft.Colors.BLACK),
            offset=ft.Offset(0, 2),
        ),
    )


def _stat_chip(icon: str, value: str, label: str) -> ft.Row:
    return ft.Row(
        controls=[
            ft.Icon(icon, size=13, opacity=0.4),
            ft.Text(value, size=12, weight=ft.FontWeight.W_500),
            ft.Text(label, size=10, opacity=0.4),
        ],
        spacing=4,
        tight=True,
    )


def _build_warning_row(warning: str) -> list[ft.Control]:
    return [
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=13, color=ft.Colors.AMBER),
                    ft.Text(
                        warning,
                        size=10,
                        color=ft.Colors.AMBER,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                ],
                spacing=4,
                tight=True,
            ),
            padding=ft.Padding(left=4, right=4, top=2, bottom=2),
            border_radius=4,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.AMBER),
        ),
    ]
