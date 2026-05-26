"""About section panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.config import get_assets_path
from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_GITHUB_URL = "https://github.com/knqiufan/Misaka"


class AboutPanel(ft.Container):
    """Panel displaying application info, author, and GitHub link."""

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
        github_icon_path = str(get_assets_path() / "GitHub.png")
        github_btn = ft.IconButton(
            icon=ft.Image(
                src=github_icon_path,
                width=18,
                height=18,
                fit=ft.BoxFit.CONTAIN,
            ),
            tooltip=t("settings.about_github"),
            on_click=self._open_github,
            style=ft.ButtonStyle(padding=6, shape=ft.CircleBorder()),
        )

        self.content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(
                                    t("settings.about"),
                                    size=16,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(t("settings.about_app"), size=13),
                                ft.Text(
                                    t("settings.about_desc"), size=12, opacity=0.6,
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            t("settings.about_author"),
                                            size=12,
                                            opacity=0.7,
                                        ),
                                        github_btn,
                                    ],
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=8,
                            expand=True,
                        ),
                    ],
                    expand=True,
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _open_github(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return

        async def _launch() -> None:
            await page.launch_url(_GITHUB_URL)

        page.run_task(_launch)
