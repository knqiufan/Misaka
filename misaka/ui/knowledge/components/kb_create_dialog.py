"""Create / edit knowledge base dialog."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    make_button,
    make_dropdown,
    make_form_dialog,
    make_text_button,
    make_text_field,
)

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)


def show_kb_create_dialog(
    state: AppState,
    *,
    kb_id: str | None = None,
    on_saved: Callable | None = None,
) -> None:
    """Open a dialog for creating or editing a knowledge base."""
    page = state.page
    kb_svc = state.get_service("kb_service")
    router_svc = state.get_service("router_config_service")
    if not kb_svc or not router_svc:
        return

    is_edit = kb_id is not None
    kb = kb_svc.get(kb_id) if is_edit else None

    embed_models = router_svc.get_available_embedding_models()
    rerank_models = router_svc.get_available_reranker_models()

    # ── Basic fields ──────────────────────────────────────────────────
    name_field = make_text_field(
        label=t("kb.name"),
        value=kb.name if kb else "",
        autofocus=True,
    )
    desc_field = make_text_field(
        label=t("kb.desc"),
        value=kb.description if kb else "",
        multiline=True,
        min_lines=2,
        max_lines=4,
    )

    # ── Model dropdowns ───────────────────────────────────────────────
    embed_options = _build_model_options(embed_models)
    embed_dd = make_dropdown(
        label=t("kb.embedding_model"),
        options=embed_options,
        value=_find_model_key(
            embed_models, kb.embedding_model_id, kb.embedding_router_config_id,
        ) if kb else None,
    )
    if not embed_options:
        embed_dd.hint_text = t("kb.no_embedding_models")

    rerank_options = [ft.dropdown.Option(key="", text=t("kb.reranker_model_none"))]
    rerank_options.extend(_build_model_options(rerank_models))
    rerank_dd = make_dropdown(
        label=t("kb.reranker_model"),
        options=rerank_options,
        value=_find_model_key(
            rerank_models, kb.reranker_model_id, kb.reranker_router_config_id,
        ) if kb else "",
    )

    # ── Advanced settings (collapsible) ───────────────────────────────
    chunk_size_field = make_text_field(
        label=t("kb.chunk_size"),
        value=str(kb.chunk_size if kb else 512),
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    chunk_overlap_field = make_text_field(
        label=t("kb.chunk_overlap"),
        value=str(kb.chunk_overlap if kb else 64),
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    top_k_field = make_text_field(
        label=t("kb.top_k"),
        value=str(kb.top_k if kb else 5),
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    threshold_field = make_text_field(
        label=t("kb.similarity_threshold"),
        value=str(kb.similarity_threshold if kb else 0.0),
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    reranker_top_k_field = make_text_field(
        label=t("kb.reranker_top_k"),
        value=str(kb.reranker_top_k if kb else 3),
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    advanced_icon = ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, opacity=0.5)
    advanced_section = ft.Column(
        controls=[
            ft.Row(controls=[chunk_size_field, chunk_overlap_field], spacing=8),
            ft.Row(controls=[top_k_field, threshold_field], spacing=8),
            reranker_top_k_field,
        ],
        spacing=8,
        visible=False,
        tight=True,
    )

    def _toggle_advanced(_: ft.ControlEvent) -> None:
        advanced_section.visible = not advanced_section.visible
        advanced_icon.name = (
            ft.Icons.KEYBOARD_ARROW_UP if advanced_section.visible
            else ft.Icons.KEYBOARD_ARROW_DOWN
        )
        advanced_icon.update()
        advanced_section.update()

    # ── Form layout ───────────────────────────────────────────────────
    form_content = ft.Column(
        controls=[
            name_field,
            desc_field,
            ft.Container(height=4),
            embed_dd,
            rerank_dd,
            ft.Container(height=2),
            ft.TextButton(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.TUNE, size=14, opacity=0.6),
                        ft.Text(t("kb.advanced_settings"), size=12, opacity=0.6),
                        advanced_icon,
                    ],
                    spacing=4,
                    tight=True,
                ),
                on_click=_toggle_advanced,
            ),
            advanced_section,
        ],
        spacing=10,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # ── Save logic ────────────────────────────────────────────────────
    def _save(_: ft.ControlEvent) -> None:
        name = (name_field.value or "").strip()
        if not name:
            name_field.error_text = t("kb.name_required")
            name_field.update()
            return
        if not embed_dd.value:
            embed_dd.error_text = t("kb.embedding_model_required")
            embed_dd.update()
            return

        embed_info = _parse_model_key(embed_dd.value)
        rerank_info = _parse_model_key(rerank_dd.value) if rerank_dd.value else None

        kwargs = {
            "chunk_size": _safe_int(chunk_size_field.value, 512),
            "chunk_overlap": _safe_int(chunk_overlap_field.value, 64),
            "top_k": _safe_int(top_k_field.value, 5),
            "similarity_threshold": _safe_float(threshold_field.value, 0.0),
            "reranker_top_k": _safe_int(reranker_top_k_field.value, 3),
        }

        if is_edit and kb:
            kb_svc.update(
                kb.id,
                name=name,
                description=desc_field.value or "",
                embedding_model_id=embed_info[0],
                embedding_router_config_id=embed_info[1],
                reranker_model_id=rerank_info[0] if rerank_info else "",
                reranker_router_config_id=rerank_info[1] if rerank_info else "",
                **kwargs,
            )
        else:
            kb_svc.create(
                name=name,
                description=desc_field.value or "",
                embedding_model_id=embed_info[0],
                embedding_router_config_id=embed_info[1],
                reranker_model_id=rerank_info[0] if rerank_info else "",
                reranker_router_config_id=rerank_info[1] if rerank_info else "",
                **kwargs,
            )

        page.pop_dialog()
        if on_saved:
            on_saved()

    dlg = make_form_dialog(
        title=t("kb.edit") if is_edit else t("kb.create"),
        icon=ft.Icons.MENU_BOOK,
        content=form_content,
        actions=[
            make_text_button(t("common.cancel"), on_click=lambda _: page.pop_dialog()),
            make_button(
                t("common.save") if is_edit else t("kb.create"),
                on_click=_save,
            ),
        ],
        width=520,
    )
    page.show_dialog(dlg)


# ── Helpers ───────────────────────────────────────────────────────────

def _build_model_options(models: list) -> list[ft.dropdown.Option]:
    options: list[ft.dropdown.Option] = []
    for m in models:
        key = f"{m.model_id}||{m.router_config_id}"
        label = f"{m.model_id}  ({m.router_name})"
        options.append(ft.dropdown.Option(key=key, text=label))
    return options


def _find_model_key(models: list, model_id: str, config_id: str) -> str:
    for m in models:
        if m.model_id == model_id and m.router_config_id == config_id:
            return f"{m.model_id}||{m.router_config_id}"
    return ""


def _parse_model_key(key: str) -> tuple[str, str]:
    parts = key.split("||", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return key, ""


def _safe_int(val: str | None, default: int) -> int:
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def _safe_float(val: str | None, default: float) -> float:
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default
