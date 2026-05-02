"""Knowledge base detail page — document management."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_button, make_text_button, make_text_field
from misaka.ui.knowledge.components.document_list import build_document_table
from misaka.ui.knowledge.components.document_upload_dialog import show_upload_dialog
from misaka.ui.knowledge.components.document_viewer import show_document_viewer

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)

_STATUS_ICONS = {
    "pending": (ft.Icons.HOURGLASS_EMPTY, ft.Colors.GREY),
    "parsing": (ft.Icons.AUTORENEW, ft.Colors.AMBER),
    "embedding": (ft.Icons.MEMORY, ft.Colors.BLUE),
    "ready": (ft.Icons.CHECK_CIRCLE_OUTLINE, ft.Colors.GREEN),
    "error": (ft.Icons.ERROR_OUTLINE, ft.Colors.ERROR),
}


class KBDetailPage(ft.Column):
    """Detail page showing documents of a single knowledge base."""

    def __init__(
        self,
        state: AppState,
        kb_id: str,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._kb_id = kb_id
        self._on_back = on_back
        self._search_query = ""
        self.refresh()

    def refresh(self) -> None:
        self._load_data()
        self._build_ui()
        try:
            self.update()
        except RuntimeError as e:
            # Before the control is mounted (e.g. during __init__), ``page`` / ``update`` raise.
            if "must be added to the page first" not in str(e).lower():
                raise

    def _load_data(self) -> None:
        doc_svc = self.state.get_service("document_service")
        kb_svc = self.state.get_service("kb_service")
        if doc_svc:
            self.state.kb_documents = doc_svc.get_documents(self._kb_id)
        if kb_svc:
            kb_svc.update_statistics(self._kb_id)

    def _build_ui(self) -> None:
        kb_svc = self.state.get_service("kb_service")
        kb = kb_svc.get(self._kb_id) if kb_svc else None
        kb_name = kb.name if kb else "—"

        self._model_availability = (
            kb_svc.check_model_availability(self._kb_id) if kb_svc else None
        )
        self._embedding_available = (
            self._model_availability.get("embedding_available", True)
            if self._model_availability
            else True
        )

        header = self._build_header(kb_name, kb)
        warning_banner = self._build_warning_banner()
        doc_table = self._build_document_section()
        controls: list[ft.Control] = [header]
        if warning_banner:
            controls.append(warning_banner)
        controls.append(doc_table)
        self.controls = controls

    def _build_header(self, kb_name: str, kb) -> ft.Container:
        stats = []
        if kb:
            stats = [
                ft.Text(f"{t('kb.documents')}: {kb.document_count}", size=11, opacity=0.5),
                ft.Text("·", size=11, opacity=0.3),
                ft.Text(f"{t('kb.chunks')}: {kb.chunk_count}", size=11, opacity=0.5),
            ]

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                ft.Icons.ARROW_BACK,
                                on_click=lambda _: self._on_back(),
                                tooltip=t("kb.back_to_list"),
                                icon_size=18,
                            ),
                            ft.Text(
                                kb_name,
                                size=18,
                                weight=ft.FontWeight.W_600,
                                expand=True,
                            ),
                            make_button(
                                t("kb.doc_upload"),
                                icon=ft.Icons.UPLOAD_FILE,
                                on_click=lambda _: self._on_upload(),
                                disabled=not self._embedding_available,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(controls=stats, spacing=6) if stats else ft.Container(),
                ],
                spacing=4,
                tight=True,
            ),
            padding=ft.Padding(left=16, right=24, top=16, bottom=8),
        )

    def _build_warning_banner(self) -> ft.Container | None:
        """Build a warning banner if models are unavailable."""
        if not self._model_availability:
            return None
        messages: list[str] = []
        if not self._model_availability.get("embedding_available", True):
            messages.append(t("kb.model_unavailable_warning"))
        if not self._model_availability.get("reranker_available", True):
            messages.append(t("kb.reranker_unavailable_warning"))
        if not messages:
            return None
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=16, color=ft.Colors.AMBER),
                    ft.Text(
                        " ".join(messages),
                        size=12,
                        color=ft.Colors.AMBER,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=24, right=24, top=8, bottom=4),
            margin=ft.Margin(left=0, right=0, top=0, bottom=0),
            border_radius=6,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.AMBER),
        )

    def _build_document_section(self) -> ft.Control:
        docs = self.state.kb_documents
        filtered = self._filter_docs(docs)

        if not docs:
            return self._build_empty_docs()

        search_field = make_text_field(
            hint_text=t("kb.search_placeholder"),
            prefix_icon=ft.Icons.SEARCH,
            value=self._search_query,
            on_change=self._on_search,
            dense=True,
        )
        search_row = ft.Container(
            content=search_field,
            padding=ft.Padding(left=24, right=24, top=4, bottom=8),
        )

        table = build_document_table(
            filtered,
            on_view=self._on_view_doc,
            on_reprocess=self._on_reprocess_doc,
            on_delete=self._on_delete_doc,
        )

        return ft.Column(
            controls=[search_row, table],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _build_empty_docs(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=48, opacity=0.12),
                    ft.Text(t("kb.doc_empty"), size=14, opacity=0.45, weight=ft.FontWeight.W_500),
                    ft.Text(t("kb.doc_empty_subtitle"), size=11, opacity=0.3),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
        )

    def _filter_docs(self, docs: list) -> list:
        if not self._search_query:
            return docs
        q = self._search_query.lower()
        return [d for d in docs if q in d.file_name.lower()]

    def _on_search(self, e: ft.ControlEvent) -> None:
        self._search_query = e.data or ""
        self.refresh()

    # ── Doc actions ───────────────────────────────────────────────────

    def _on_upload(self) -> None:
        show_upload_dialog(self.state, self._kb_id, on_done=self.refresh)

    def _on_view_doc(self, doc_id: str) -> None:
        show_document_viewer(self.state, doc_id)

    def _on_reprocess_doc(self, doc_id: str) -> None:
        doc_svc = self.state.get_service("document_service")
        router_svc = self.state.get_service("router_config_service")
        kb_svc = self.state.get_service("kb_service")
        if not doc_svc or not router_svc or not kb_svc:
            return

        kb = kb_svc.get(self._kb_id)
        if not kb or not kb.embedding_model_id:
            return

        embed_models = router_svc.get_available_embedding_models()
        embed_config = _find_embed_config(embed_models, kb)
        if not embed_config:
            return

        doc = doc_svc.get_document(doc_id)
        doc_name = doc.file_name if doc else doc_id

        async def _run():
            from misaka.services.knowledge.rag.abstractions import EmbeddingConfig
            config = EmbeddingConfig(**embed_config)
            self.state.page.open(
                ft.SnackBar(
                    content=ft.Text(t("kb.doc_processing").replace("{name}", doc_name)),
                    open=True,
                )
            )
            await doc_svc.reprocess_document(doc_id, config)
            self.refresh()

        self.state.page.run_task(_run)

    def _on_delete_doc(self, doc_id: str) -> None:
        doc_svc = self.state.get_service("document_service")
        if not doc_svc:
            return
        doc = doc_svc.get_document(doc_id)
        if not doc:
            return

        page = self.state.page

        def _do_delete(_: ft.ControlEvent) -> None:
            doc_svc.delete_document(doc_id)
            kb_svc = self.state.get_service("kb_service")
            if kb_svc:
                kb_svc.update_statistics(self._kb_id)
            page.pop_dialog()
            self.refresh()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(t("kb.doc_delete"), size=16, weight=ft.FontWeight.W_600),
                content=ft.Text(
                    t("kb.doc_delete_confirm").replace("{name}", doc.file_name),
                    size=13,
                ),
                actions=[
                    make_text_button(t("common.cancel"), on_click=lambda _: page.pop_dialog()),
                    ft.TextButton(
                        t("kb.doc_delete"),
                        on_click=_do_delete,
                        style=ft.ButtonStyle(color=ft.Colors.ERROR),
                    ),
                ],
            ),
        )


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
