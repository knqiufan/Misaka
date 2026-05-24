"""Document content viewer dialog with chunked loading for large documents."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_form_dialog, make_text_button

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)

_INITIAL_CHARS = 20000
_LOAD_MORE_CHARS = 20000


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
    total_len = len(content_text)

    if not content_text.strip():
        body = _build_empty_body(doc.status, doc.error_message)
        load_more_btn = ft.Container()
    else:
        displayed = [min(_INITIAL_CHARS, total_len)]

        text_ctrl = ft.Text(
            content_text[:displayed[0]],
            selectable=True,
            size=12,
            font_family="monospace",
        )

        body = ft.Container(
            content=text_ctrl,
            padding=12,
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            max_height=500,
        )

        load_more_btn = _build_load_more_button(
            content_text, displayed, text_ctrl, total_len,
        )

    copy_btn_text = ft.Text(t("kb.doc_viewer_copy"), size=11)

    async def _on_copy(_: ft.ControlEvent) -> None:
        await ft.Clipboard().set(content_text)
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
            load_more_btn,
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


def _build_empty_body(status: str = "", error_message: str = "") -> ft.Container:
    """Build the placeholder body for empty document content."""
    if status == "error" and error_message:
        message = error_message
    elif status in ("parsing", "pending"):
        message = t("kb.doc_viewer_processing")
    elif status == "ready":
        message = t("kb.doc_viewer_no_text")
    else:
        message = t("kb.doc_viewer_empty")
    return ft.Container(
        content=ft.Text(
            message,
            size=13,
            opacity=0.4,
            italic=True,
        ),
        alignment=ft.Alignment.CENTER,
        height=200,
    )


def _build_load_more_button(
    content_text: str,
    displayed: list[int],
    text_ctrl: ft.Text,
    total_len: int,
) -> ft.Container:
    """Build a 'load more' button for chunked document display."""
    if displayed[0] >= total_len:
        return ft.Container()

    remaining = total_len - displayed[0]
    btn_text = ft.Text(
        t("kb.doc_viewer_load_more").replace(
            "{remaining}",
            _format_char_count(remaining),
        ),
        size=11,
        color=ft.Colors.PRIMARY,
    )

    def _on_load_more(_: ft.ControlEvent) -> None:
        new_end = min(displayed[0] + _LOAD_MORE_CHARS, total_len)
        text_ctrl.value = content_text[:new_end]
        displayed[0] = new_end
        text_ctrl.update()
        if new_end >= total_len:
            btn_text.value = ""
            btn_text.update()
        else:
            remaining_now = total_len - new_end
            btn_text.value = t("kb.doc_viewer_load_more").replace(
                "{remaining}", _format_char_count(remaining_now),
            )
            btn_text.update()

    return ft.Container(
        content=ft.TextButton(
            content=btn_text,
            on_click=_on_load_more,
        ),
        alignment=ft.Alignment.CENTER,
    )


def _format_char_count(chars: int) -> str:
    """Format character count for human-readable display."""
    if chars < 1000:
        return f"{chars}"
    if chars < 1000000:
        return f"{chars / 1000:.1f}K"
    return f"{chars / 1000000:.1f}M"


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
