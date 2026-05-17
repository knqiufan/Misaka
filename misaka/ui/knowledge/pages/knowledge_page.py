"""Knowledge base main page — list view and detail view."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_button, make_text_button
from misaka.ui.knowledge.components.kb_card import build_kb_card
from misaka.ui.knowledge.components.kb_create_dialog import show_kb_create_dialog
from misaka.ui.knowledge.pages.kb_detail_page import KBDetailPage

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)


class KnowledgePage(ft.Column):
    """Top-level knowledge base page with list and detail sub-views."""

    def __init__(self, state: AppState) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._detail_page: KBDetailPage | None = None
        self._showing_detail = False

    def refresh(self) -> None:
        """Rebuild the list view. Called by AppShell on navigation."""
        if self._showing_detail and self._detail_page:
            self._detail_page.refresh()
            return
        self._load_data()
        self._build_list_view()

    def _refresh_and_update(self) -> None:
        """Reload data, rebuild UI, and push the update to the page."""
        self.refresh()
        try:
            self.update()
        except RuntimeError as e:
            if "must be added to the page first" not in str(e).lower():
                raise

    def _load_data(self) -> None:
        svc = self.state.get_service("kb_service")
        if svc:
            kb = self.state.ensure_kb_state()
            kb.knowledge_bases = svc.get_all()

    def _build_list_view(self) -> None:
        self._showing_detail = False
        header = self._build_header()
        body = self._build_body()
        self.controls = [header, body]

    def _build_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(t("kb.title"), size=20, weight=ft.FontWeight.W_600),
                            ft.Text(
                                t("kb.description"),
                                size=12, opacity=0.6,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    make_button(
                        t("kb.create"),
                        icon=ft.Icons.ADD,
                        on_click=lambda _: self._on_create(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=24, right=24, top=20, bottom=12),
        )

    def _build_body(self) -> ft.Control:
        kbs = self.state.kb.knowledge_bases if self.state.kb else []
        if not kbs:
            return self._build_empty_state()
        return self._build_card_grid(kbs)

    def _build_empty_state(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.MENU_BOOK_OUTLINED,
                        size=64,
                        opacity=0.15,
                    ),
                    ft.Text(
                        t("kb.empty_title"),
                        size=16, weight=ft.FontWeight.W_500, opacity=0.5,
                    ),
                    ft.Text(
                        t("kb.empty_subtitle"),
                        size=12, opacity=0.35,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
        )

    def _build_card_grid(self, kbs: list) -> ft.Column:
        kb_svc = self.state.get_service("kb_service")
        cards = [
            build_kb_card(
                kb,
                warning=self._get_kb_warning(kb_svc, kb.id),
                on_manage=lambda _, kid=kb.id: self._on_manage(kid),
                on_edit=lambda _, kid=kb.id: self._on_edit(kid),
                on_delete=lambda _, kid=kb.id: self._on_delete(kid),
            )
            for kb in kbs
        ]
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.ResponsiveRow(
                        controls=[
                            ft.Container(content=card, col={"sm": 12, "md": 6, "lg": 4})
                            for card in cards
                        ],
                        spacing=12,
                        run_spacing=12,
                    ),
                    padding=ft.Padding(left=24, right=24, top=0, bottom=24),
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _get_kb_warning(self, kb_svc, kb_id: str) -> str | None:
        """Build a warning string if embedding/reranker models are unavailable."""
        if not kb_svc:
            return None
        availability = kb_svc.check_model_availability(kb_id)
        warnings: list[str] = []
        if not availability["embedding_available"]:
            warnings.append(t("kb.model_unavailable_warning"))
        if not availability["reranker_available"]:
            warnings.append(t("kb.reranker_unavailable_warning"))
        return " ".join(warnings) if warnings else None

    # ── Actions ───────────────────────────────────────────────────────

    def _on_create(self) -> None:
        show_kb_create_dialog(self.state, on_saved=self._refresh_and_update)

    def _on_edit(self, kb_id: str) -> None:
        show_kb_create_dialog(self.state, kb_id=kb_id, on_saved=self._refresh_and_update)

    def _on_manage(self, kb_id: str) -> None:
        self._showing_detail = True
        self._detail_page = KBDetailPage(
            state=self.state,
            kb_id=kb_id,
            on_back=self._back_to_list,
        )
        self.controls = [self._detail_page]
        self.update()

    def _on_delete(self, kb_id: str) -> None:
        svc = self.state.get_service("kb_service")
        if not svc:
            return
        kb = svc.get(kb_id)
        if not kb:
            return

        page = self.state.page

        def _do_delete(_: ft.ControlEvent) -> None:
            page.pop_dialog()
            page.run_task(self._async_delete_kb, kb_id)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(t("kb.delete"), size=16, weight=ft.FontWeight.W_600),
                content=ft.Text(
                    t("kb.delete_confirm").replace("{name}", kb.name),
                    size=13,
                ),
                actions=[
                    make_text_button(t("common.cancel"), on_click=lambda _: page.pop_dialog()),
                    ft.TextButton(
                        t("kb.delete"),
                        on_click=_do_delete,
                        style=ft.ButtonStyle(color=ft.Colors.ERROR),
                    ),
                ],
            ),
        )

    async def _async_delete_kb(self, kb_id: str) -> None:
        svc = self.state.get_service("kb_service")
        if svc:
            svc.delete(kb_id)
        self._refresh_and_update()

    def _back_to_list(self) -> None:
        self._showing_detail = False
        self._detail_page = None
        self._refresh_and_update()
