"""Claude Code & Misaka update settings panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_badge,
    make_button,
    make_outlined_button,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_MISAKA_RELEASES_URL = "https://github.com/knqiufan/Misaka/releases/latest"


class UpdatePanel(ft.Container):
    """Panel combining Claude Code update check and Misaka update sections."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)
        self._update_checking: bool = False
        self._update_progress_msg: str = ""
        self._build_ui()

    def refresh(self) -> None:
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.content = ft.Column(
            controls=[
                self._build_claude_update_section(),
                ft.Divider(height=1, thickness=0.5, opacity=0.3),
                self._build_misaka_update_section(),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # ------------------------------------------------------------------
    # Claude Code update
    # ------------------------------------------------------------------

    def _build_claude_update_section(self) -> ft.Control:
        result = self.state.update_check_result
        is_checking = self._update_checking
        is_updating = self.state.update_in_progress

        current = result.current_version if result else None
        latest = result.latest_version if result else None
        has_update = result.update_available if result else False

        version_rows = self._build_version_rows(current, latest, has_update)
        action_btn = self._build_action_button(is_checking, is_updating, has_update)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.claude_update"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(expand=True),
                            action_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(t("settings.claude_update_desc"), size=12, opacity=0.6),
                    *version_rows,
                ],
                spacing=12,
            ),
        )

    def _build_version_rows(
        self,
        current: str | None,
        latest: str | None,
        has_update: bool,
    ) -> list[ft.Control]:
        rows: list[ft.Control] = []
        if current:
            rows.append(
                ft.Text(
                    f"{t('settings.current_version')}: {current}",
                    size=13, opacity=0.8,
                ),
            )
        if latest:
            badge = self._make_status_badge(has_update)
            rows.append(
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{t('settings.latest_version')}: {latest}",
                            size=13, opacity=0.8,
                        ),
                        badge,
                    ],
                    spacing=8,
                ),
            )
        if self._update_progress_msg:
            rows.append(
                ft.Text(self._update_progress_msg, size=12, opacity=0.6),
            )
        return rows

    @staticmethod
    def _make_status_badge(has_update: bool) -> ft.Control:
        if has_update:
            return make_badge(t("settings.update_available"), bgcolor=WARNING_AMBER)
        return make_badge(
            t("settings.up_to_date"),
            bgcolor=SUCCESS_GREEN,
            icon=ft.Icons.CHECK_CIRCLE,
        )

    def _build_action_button(
        self, is_checking: bool, is_updating: bool, has_update: bool,
    ) -> ft.Control:
        if is_checking or is_updating:
            label = t("settings.checking") if is_checking else t("update.updating")
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2),
                    ft.Text(label, size=12, opacity=0.7),
                ],
                spacing=6,
            )
        if has_update:
            return make_button(
                t("update.update_now"),
                icon=ft.Icons.SYSTEM_UPDATE,
                on_click=self._handle_perform_update,
            )
        return make_outlined_button(
            t("settings.check_update"),
            icon=ft.Icons.REFRESH,
            on_click=self._handle_check_update,
        )

    # ------------------------------------------------------------------
    # Claude Code update handlers
    # ------------------------------------------------------------------

    def _handle_check_update(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return
        self._update_checking = True
        self._build_ui()
        self.state.update()
        page.run_task(self._do_check_update)

    async def _do_check_update(self) -> None:
        svc = self.state.get_service("update_check_service")
        if svc:
            self.state.update_check_result = await svc.check_for_update()
        self._update_checking = False
        self._build_ui()
        self.state.update()

    def _handle_perform_update(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return
        self.state.update_in_progress = True
        self._update_progress_msg = ""
        self._build_ui()
        self.state.update()
        page.run_task(self._do_perform_update)

    async def _do_perform_update(self) -> None:
        svc = self.state.get_service("update_check_service")
        if not svc:
            self.state.update_in_progress = False
            self._build_ui()
            self.state.update()
            return

        def on_progress(msg: str) -> None:
            self._update_progress_msg = msg

        success = await svc.perform_update(on_progress=on_progress)
        self.state.update_in_progress = False
        if success:
            self.state.update_check_result = await svc.check_for_update()
        self._build_ui()
        self.state.update()

    # ------------------------------------------------------------------
    # Misaka update
    # ------------------------------------------------------------------

    def _build_misaka_update_section(self) -> ft.Control:
        from misaka import __version__

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.misaka_update"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(expand=True),
                            make_outlined_button(
                                t("settings.misaka_open_releases"),
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=self._handle_open_releases,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(t("settings.misaka_update_desc"), size=12, opacity=0.6),
                    ft.Text(
                        f"{t('settings.misaka_version')}: {__version__}",
                        size=13, opacity=0.8,
                    ),
                ],
                spacing=12,
            ),
        )

    def _handle_open_releases(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return

        async def _launch() -> None:
            await page.launch_url(_MISAKA_RELEASES_URL)

        page.run_task(_launch)
