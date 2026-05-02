"""Document content viewer dialog."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_form_dialog, make_icon_button, make_text_button

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)


def show_document_viewer(state: AppState, doc_id: str) -> None:
    """Show a dialog displaying the parsed plain-text content of a document."""
    page = state.page
    doc_svc = state.get_service("document_service")
    if not doc_svc:
        return

    doc = doc_svc.get_document(doc_id)
    if not doc:
        return

    content_text = doc.content_text or ""
    file_info = _build_file_info(doc)

    if not content_text.strip():
        body = ft.Container(
            content=ft.Text(
                t("kb.doc_viewer_empty"),
                size=13,
                opacity=0.4,
                italic=True,
            ),
            alignment=ft.Alignment.CENTER,
            height=200,
        )
    else:
        body = ft.Container(
            content=ft.Text(
                content_text,
                selectable=True,
                size=12,
                font_family="monospace",
            ),
            padding=12,
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            max_height=500,
        )

    copy_btn_text = ft.Text(t("kb.doc_viewer_copy"), size=11)

    def _on_copy(_: ft.ControlEvent) -> None:
        page.set_clipboard(content_text)
        copy_btn_text.value = t("kb.doc_viewer_copied")
        copy_btn_text.update()

    dlg_content = ft.Column(
        controls=[
            file_info,
            ft.Row(
                controls=[
                    ft.Container(expand=True),
                    ft.TextButton(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CONTENT_COPY, size=14),
                                copy_btn_text,
                            ],
                            spacing=4,
                            tight=True,
                        ),
                        on_click=_on_copy,
                    ),
                ],
            ),
            body,
        ],
        spacing=8,
        tight=True,
        scroll=ft.ScrollMode.AUTO,
    )

    dlg = make_form_dialog(
        title=t("kb.doc_viewer_title"),
        subtitle=doc.file_name,
        icon=ft.Icons.ARTICLE,
        content=dlg_content,
        actions=[
            make_text_button(t("common.close"), on_click=lambda _: page.pop_dialog()),
        ],
        width=700,
    )
    page.show_dialog(dlg)


def _build_file_info(doc) -> ft.Row:
    """Build a compact file metadata summary row."""
    size = _format_size(doc.file_size)
    return ft.Row(
        controls=[
            _info_chip(t("kb.doc_type"), doc.file_type.upper()),
            _info_chip(t("kb.doc_size"), size),
            _info_chip(t("kb.doc_chunks"), str(doc.chunk_count)),
        ],
        spacing=16,
    )


def _info_chip(label: str, value: str) -> ft.Column:
    return ft.Column(
        controls=[
            ft.Text(label, size=9, opacity=0.4),
            ft.Text(value, size=12, weight=ft.FontWeight.W_500),
        ],
        spacing=2,
        tight=True,
    )


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
