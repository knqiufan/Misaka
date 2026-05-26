"""Permission mode settings panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.config import SettingKeys
from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_PERMISSION_MODES = [
    ("default", "settings.perm_default", "settings.perm_default_desc"),
    ("acceptEdits", "settings.perm_accept_edits", "settings.perm_accept_edits_desc"),
    ("bypassPermissions", "settings.perm_bypass", "settings.perm_bypass_desc"),
]


class PermissionPanel(ft.Container):
    """Panel for selecting the Claude Code permission mode."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)
        self._build_ui()

    def refresh(self) -> None:
        self._build_ui()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        current_mode = self._load_current_mode()
        mode_options = self._build_mode_options(current_mode)

        radio_group = ft.RadioGroup(
            value=current_mode,
            content=ft.Column(controls=mode_options, spacing=4),
            on_change=self._on_mode_change,
        )

        self.content = ft.Column(
            controls=[
                ft.Text(
                    t("settings.permission_mode"),
                    size=16,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(t("settings.permission_mode_desc"), size=12, opacity=0.6),
                radio_group,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _load_current_mode(self) -> str:
        if self.db:
            saved = self.db.get_setting("permission_mode")
            if saved:
                return saved
        return "default"

    @staticmethod
    def _build_mode_options(current_mode: str) -> list[ft.Control]:
        options: list[ft.Control] = []
        for mode_id, label_key, desc_key in _PERMISSION_MODES:
            tile = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Radio(value=mode_id, label=""),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    t(label_key),
                                    size=13,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(t(desc_key), size=11, opacity=0.6),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            )
            options.append(tile)
        return options

    def _on_mode_change(self, e: ft.ControlEvent) -> None:
        mode = e.data or e.control.value
        if not mode:
            return
        settings_svc = self.state.get_service("settings_service")
        if settings_svc:
            settings_svc.set(SettingKeys.PERMISSION_MODE, mode)
        elif self.db:
            self.db.set_setting(SettingKeys.PERMISSION_MODE, mode)
