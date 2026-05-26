"""Appearance & language settings panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.ui.settings.pages.appearance_section import (
    build_appearance_section,
    build_language_section,
    change_accent_color,
    change_language,
    change_theme,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState


class AppearancePanel(ft.Container):
    """Panel combining theme/accent-color selection and language switching."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
        on_theme_change: Callable[[str], None] | None = None,
        on_locale_change: Callable[[str], None] | None = None,
        rebuild_settings_ui: Callable[[], None] | None = None,
        show_language_only: bool = False,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self._on_theme_change = on_theme_change
        self._on_locale_change = on_locale_change
        self._rebuild_settings_ui = rebuild_settings_ui
        self._show_language_only = show_language_only
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)
        self._build_ui()

    def refresh(self) -> None:
        self._build_ui()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        controls: list[ft.Control] = []

        if not self._show_language_only:
            appearance_section = build_appearance_section(
                self.state,
                on_theme_click=self._handle_theme_click,
                on_accent_click=self._handle_accent_click,
            )
            controls.append(appearance_section)

        language_section = build_language_section(
            self.state,
            on_language_click=self._handle_language_click,
        )
        controls.append(language_section)

        self.content = ft.Column(
            controls=controls,
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _handle_theme_click(self, mode: str) -> None:
        rebuild = self._rebuild_settings_ui or self._build_ui
        change_theme(self.state, mode, self._on_theme_change, rebuild)

    def _handle_accent_click(self, color: str) -> None:
        rebuild = self._rebuild_settings_ui or self._build_ui
        change_accent_color(self.state, color, self.db, rebuild)

    def _handle_language_click(self, locale: str) -> None:
        rebuild = self._rebuild_settings_ui or self._build_ui
        change_language(
            self.state, locale, self.db,
            self._on_locale_change, rebuild,
        )
