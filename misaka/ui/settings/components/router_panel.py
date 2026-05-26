"""Router / provider configuration panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.ui.settings.pages.provider_section import build_router_section, show_router_form

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState


class RouterPanel(ft.Container):
    """Panel wrapping the router/provider configuration section."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)
        self._router_list: ft.Column = ft.Column(spacing=4)
        self._build_ui()

    def refresh(self) -> None:
        self._build_ui()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        section = build_router_section(
            self.state,
            self._router_list,
            on_add_click=self._show_add_router_dialog,
        )
        self.content = ft.Column(
            controls=[section],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _show_add_router_dialog(self, e: ft.ControlEvent) -> None:
        if e.page:
            show_router_form(
                self.state, e.page, config=None, router_list=self._router_list,
            )
