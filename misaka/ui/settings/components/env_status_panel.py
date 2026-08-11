"""Environment status panel — tool availability checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    ERROR_RED,
    RADIUS_LG,
    SUCCESS_GREEN,
    make_badge,
    make_button,
    make_outlined_button,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.services.skills.env_check_service import InstallResult
    from misaka.state import AppState


class EnvStatusPanel(ft.Container):
    """Panel showing installed/missing tool status with install actions."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)
        self._env_checking: bool = False
        self._env_installing_tool: str | None = None
        self._install_message: str | None = None
        self._install_error = False
        self._build_ui()

    def refresh(self) -> None:
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        result = self.state.env_check_result
        tool_rows = self._build_tool_status_rows(result)
        header_btn = self._build_header_button()

        self.content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            t("settings.env_status"),
                            size=16,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Container(expand=True),
                        header_btn,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(t("settings.env_status_desc"), size=12, opacity=0.6),
                ft.Column(controls=tool_rows, spacing=8),
                self._build_install_status(),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _build_install_status(self) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.ERROR if self._install_error else ft.Icons.INFO,
                        color=ERROR_RED if self._install_error else ft.Colors.PRIMARY,
                        size=18,
                    ),
                    ft.Text(
                        self._install_message or "",
                        color=ERROR_RED if self._install_error else None,
                        size=12,
                        expand=True,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(
                0.08,
                ERROR_RED if self._install_error else ft.Colors.PRIMARY,
            ),
            visible=bool(self._install_message),
        )

    def _build_header_button(self) -> ft.Control:
        if self._env_checking:
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2),
                    ft.Text(t("settings.checking"), size=12, opacity=0.7),
                ],
                spacing=6,
            )
        return make_outlined_button(
            t("settings.recheck"),
            icon=ft.Icons.REFRESH,
            on_click=self._handle_recheck,
        )

    def _build_tool_status_rows(self, result) -> list[ft.Control]:
        if not result:
            return [
                ft.Text(t("settings.checking"), size=12, italic=True, opacity=0.5),
            ]
        return [self._build_tool_card(tool) for tool in result.tools]

    def _build_tool_card(self, tool) -> ft.Control:
        is_installed = tool.is_installed
        is_installing = self._env_installing_tool == tool.name

        status_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE if is_installed else ft.Icons.CANCEL,
            color=SUCCESS_GREEN if is_installed else ERROR_RED,
            size=22,
        )

        if tool.version:
            version_text = f"v{tool.version}"
        elif tool.is_installed:
            version_text = t("settings.env_version_unknown")
        else:
            version_text = t("env_check.not_installed")

        right_widget = self._build_action_widget(tool, is_installed, is_installing)

        return ft.Container(
            content=ft.Row(
                controls=[
                    status_icon,
                    ft.Column(
                        controls=[
                            ft.Text(tool.name, size=13, weight=ft.FontWeight.W_500),
                            ft.Text(version_text, size=11, opacity=0.6),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    right_widget,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=RADIUS_LG,
            border=ft.Border.all(
                1,
                SUCCESS_GREEN if is_installed
                else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
        )

    def _build_action_widget(self, tool, is_installed: bool, is_installing: bool) -> ft.Control:
        if is_installed:
            return make_badge(t("env_check.installed"), bgcolor=SUCCESS_GREEN)
        if is_installing:
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=14, height=14, stroke_width=2),
                    ft.Text(t("env_check.installing"), size=11, opacity=0.7),
                ],
                spacing=6,
            )
        button = make_button(
            t("env_check.install"),
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda e, name=tool.name: self._handle_install(e, name),
        )
        button.disabled = self._env_installing_tool is not None
        return button

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_recheck(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return
        self._env_checking = True
        self._install_message = None
        self._install_error = False
        self._build_ui()
        self.state.update()
        page.run_task(self._do_recheck)

    async def _do_recheck(self) -> None:
        svc = self.state.get_service("env_check_service")
        if svc:
            self.state.env_check_result = await svc.check_all()
        self._env_checking = False
        self._build_ui()
        self.state.update()

    def _handle_install(self, e: ft.ControlEvent, tool_name: str) -> None:
        page = e.page
        if not page:
            return
        self._env_installing_tool = tool_name
        self._install_message = None
        self._install_error = False
        self._build_ui()
        self.state.update()

        async def _install_task() -> None:
            await self._do_install(tool_name)

        page.run_task(_install_task)

    async def _do_install(self, tool_name: str) -> None:
        svc = self.state.get_service("env_check_service")
        if svc:
            result = await svc.install_tool(tool_name, on_progress=self._on_install_progress)
            self.state.env_check_result = await svc.check_all()
            self._finish_install(result)
        self._env_installing_tool = None
        self._build_ui()
        self.state.update()

    def _on_install_progress(self, message: str) -> None:
        self._install_message = t(
            "env_check.installing_tool",
            tool=self._env_installing_tool or "",
        )
        self._install_error = False
        self._build_ui()
        self.state.update()

    def _finish_install(self, result: InstallResult) -> None:
        self._install_message = (
            t("env_check.install_success", tool=result.tool_name)
            if result.success
            else t("env_check.install_failed_detail", error=result.message)
        )
        self._install_error = not result.success
