"""Document upload dialog."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_form_dialog, make_text_button

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = ["*.txt", "*.md", "*.markdown", "*.docx", "*.xlsx", "*.pdf"]


def show_upload_dialog(
    state: AppState,
    kb_id: str,
    *,
    on_done: Callable | None = None,
) -> None:
    """Open a file picker and upload selected files."""
    page = state.page
    kb_svc = state.get_service("kb_service")
    router_svc = state.get_service("router_config_service")
    doc_svc = state.get_service("document_service")
    if not kb_svc or not router_svc or not doc_svc:
        return

    kb = kb_svc.get(kb_id)
    if not kb or not kb.embedding_model_id:
        return

    embed_models = router_svc.get_available_embedding_models()
    embed_config = _find_embed_config(embed_models, kb)
    if not embed_config:
        return

    status_text = ft.Text("", size=12, opacity=0.6)
    progress_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
    progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
    results_column = ft.Column(controls=[], spacing=4, tight=True)

    dlg_content = ft.Column(
        controls=[
            ft.Row(
                controls=[progress_ring, status_text],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress_bar,
            results_column,
        ],
        spacing=12,
        tight=True,
        width=400,
    )

    dlg = make_form_dialog(
        title=t("kb.doc_upload_title"),
        icon=ft.Icons.UPLOAD_FILE,
        content=dlg_content,
        actions=[
            make_text_button(t("common.cancel"), on_click=lambda _: _close()),
        ],
        width=480,
    )

    def _close() -> None:
        page.pop_dialog()

    upload_started = False

    async def _pick_and_upload() -> None:
        nonlocal upload_started
        picker = ft.FilePicker()
        page.services.append(picker)
        page.update()
        try:
            files = await picker.pick_files(
                dialog_title=t("kb.doc_upload_title"),
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[ext.lstrip("*.") for ext in _ALLOWED_EXTENSIONS],
                allow_multiple=True,
            )
        finally:
            if picker in page.services:
                page.services.remove(picker)
                page.update()

        if not files:
            return
        file_paths = [f.path for f in files if f.path]
        if not file_paths:
            return

        upload_started = True
        page.show_dialog(dlg)
        try:
            await _upload_paths_async(
                page,
                doc_svc,
                kb_svc,
                kb_id,
                embed_config,
                status_text,
                progress_ring,
                progress_bar,
                results_column,
                file_paths,
            )
        except Exception:
            logger.exception("Upload failed")
        finally:
            if on_done:
                on_done()

    page.run_task(_pick_and_upload)


async def _upload_paths_async(
    page: ft.Page,
    doc_svc,
    kb_svc,
    kb_id: str,
    embed_config: dict,
    status_text: ft.Text,
    progress_ring: ft.ProgressRing,
    progress_bar: ft.ProgressBar,
    results_column: ft.Column,
    file_paths: list[str],
) -> None:
    from misaka.services.knowledge.rag.abstractions import EmbeddingConfig

    config = EmbeddingConfig(**embed_config)
    total = len(file_paths)
    success = 0

    progress_ring.visible = True
    progress_ring.update()

    progress_bar.visible = True
    progress_bar.value = 0
    progress_bar.update()

    for i, path in enumerate(file_paths):
        import os

        name = os.path.basename(path)
        status_text.value = t("kb.doc_processing").replace("{name}", name)
        status_text.update()

        try:
            doc = await doc_svc.upload_document(kb_id, path, config)
            if doc.status == "ready":
                success += 1
                _add_result(results_column, name, "ready")
            else:
                _add_result(results_column, name, "error", doc.error_message)
        except Exception as exc:
            _handle_upload_error(results_column, name, exc)

        progress_bar.value = (i + 1) / total
        progress_bar.update()
        await asyncio.sleep(0)

    progress_ring.visible = False
    progress_ring.update()
    progress_bar.visible = False
    progress_bar.update()

    if success == total:
        status_text.value = t("kb.doc_upload_success").replace("{count}", str(success))
    else:
        status_text.value = (
            t("kb.doc_upload_partial")
            .replace("{success}", str(success))
            .replace("{total}", str(total))
        )
    status_text.update()
    kb_svc.update_statistics(kb_id)


def _handle_upload_error(
    column: ft.Column,
    name: str,
    exc: Exception,
) -> None:
    err_name = type(exc).__name__
    err_str = str(exc)
    if "Duplicate" in err_name:
        _add_result(column, name, "duplicate")
    elif "too large" in err_str.lower() or "maximum" in err_str.lower():
        _add_result(column, name, "error", t("kb.doc_file_too_large"))
    elif "Unsupported file type" in err_str:
        _add_result(column, name, "error", t("kb.doc_unsupported"))
    else:
        _add_result(column, name, "error", err_str)


def _add_result(
    column: ft.Column,
    file_name: str,
    status: str,
    error_msg: str | None = None,
) -> None:
    icon_map = {
        "ready": (ft.Icons.CHECK_CIRCLE_OUTLINE, ft.Colors.GREEN),
        "error": (ft.Icons.ERROR_OUTLINE, ft.Colors.ERROR),
        "duplicate": (ft.Icons.CONTENT_COPY, ft.Colors.AMBER),
    }
    icon, color = icon_map.get(status, (ft.Icons.HELP_OUTLINE, ft.Colors.GREY))

    row = ft.Row(
        controls=[
            ft.Icon(icon, size=14, color=color),
            ft.Text(
                file_name,
                size=11,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                expand=True,
            ),
            ft.Text(
                status, size=10, color=color, opacity=0.7,
                tooltip=error_msg if error_msg else None,
            ),
        ],
        spacing=6,
    )
    column.controls.append(row)
    column.update()


def _find_embed_config(models: list, kb) -> dict | None:
    for m in models:
        same_model = m.model_id == kb.embedding_model_id
        same_router = m.router_config_id == kb.embedding_router_config_id
        if same_model and same_router:
            return {
                "model_id": m.model_id,
                "base_url": m.base_url,
                "api_key": m.api_key,
            }
    return None
