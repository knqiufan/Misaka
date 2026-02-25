"""Environment check dialog component.

Full-screen overlay dialog shown at startup if any required tools
are missing. Displays a status card per tool with install buttons,
progress indicators, and re-check functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.state import AppState


class EnvCheckDialog(ft.Column):
    """Full-screen overlay dialog showing environment check results.

    Displayed on startup if any required tools are missing.
    Shows a card per tool with status icon, version, and install button.
    """

    def __init__(
        self,
        state: AppState,
        on_install: Callable[[str], None] | None = None,
        on_dismiss: Callable[[], None] | None = None,
        on_recheck: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )
        self.state = state
        self._on_install = on_install
        self._on_dismiss = on_dismiss
        self._on_recheck = on_recheck
        self._installing_tool: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        check_result = self.state.env_check_result
        if not check_result:
            self.visible = False
            self.controls = []
            return

        self.visible = True

        # Build tool cards
        tool_cards: list[ft.Control] = []
        for tool in check_result.tools:
            tool_cards.append(self._build_tool_card(tool))

        # All-ready message
        all_ready_msg = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=20),
                    ft.Text(
                        t("env_check.all_ready"),
                        size=14,
                        color=ft.Colors.GREEN,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(vertical=8),
            visible=check_result.all_installed,
        )

        # Action buttons
        skip_btn = ft.OutlinedButton(
            content=t("env_check.skip"),
            on_click=self._handle_dismiss,
        )
        recheck_btn = ft.Button(
            content=t("env_check.check_again"),
            icon=ft.Icons.REFRESH,
            on_click=self._handle_recheck,
        )

        actions = ft.Row(
            controls=[
                ft.Container(expand=True),
                skip_btn,
                recheck_btn,
            ],
            spacing=12,
        )

        # Dialog card
        dialog_content = ft.Container(
            content=ft.Column(
                controls=[
                    # Title row
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.BUILD_CIRCLE, size=28, color=ft.Colors.PRIMARY),
                            ft.Text(
                                t("env_check.title"),
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                icon_size=20,
                                on_click=self._handle_dismiss,
                                style=ft.ButtonStyle(padding=4),
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        t("env_check.description"),
                        size=13,
                        opacity=0.7,
                    ),
                    ft.Divider(height=1),
                    # Tool cards
                    ft.Column(
                        controls=tool_cards,
                        spacing=8,
                    ),
                    all_ready_msg,
                    ft.Divider(height=1),
                    actions,
                ],
                spacing=12,
            ),
            width=520,
            padding=24,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            ),
        )

        # Overlay background
        self.controls = [
            ft.Container(
                content=dialog_content,
                alignment=ft.Alignment.CENTER,
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK),
            )
        ]
        self.expand = True

    def _build_tool_card(self, tool) -> ft.Control:
        """Build a card for one tool.

        Shows:
        - Green check / red X icon
        - Tool name and version (or "Not installed")
        - "Install" button (if not installed) or "Installed" badge
        - Progress indicator during install
        """
        is_installed = tool.is_installed
        is_installing = self._installing_tool == tool.name

        # Status icon
        if is_installed:
            status_icon = ft.Icon(
                ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=24
            )
        else:
            status_icon = ft.Icon(
                ft.Icons.CANCEL, color=ft.Colors.ERROR, size=24
            )

        # Version / status text
        if is_installed:
            version_text = f"v{tool.version}" if tool.version else t("env_check.installed")
            status_badge = ft.Container(
                content=ft.Text(
                    t("env_check.installed"),
                    size=11,
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.BOLD,
                ),
                bgcolor=ft.Colors.GREEN,
                border_radius=4,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            )
        else:
            version_text = t("env_check.not_installed")
            if is_installing:
                status_badge = ft.Row(
                    controls=[
                        ft.ProgressRing(width=16, height=16, stroke_width=2),
                        ft.Text(t("env_check.installing"), size=11, opacity=0.7),
                    ],
                    spacing=6,
                )
            else:
                status_badge = ft.Row(
                    controls=[
                        ft.Button(
                            content=t("env_check.install"),
                            icon=ft.Icons.DOWNLOAD,
                            on_click=lambda e, name=tool.name: self._handle_install(name),
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.PRIMARY,
                                color=ft.Colors.ON_PRIMARY,
                            ),
                        ),
                    ],
                    spacing=6,
                )

        return ft.Container(
            content=ft.Row(
                controls=[
                    status_icon,
                    ft.Column(
                        controls=[
                            ft.Text(
                                tool.name,
                                size=14,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                version_text,
                                size=12,
                                opacity=0.6,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    status_badge,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=8,
            border=ft.Border.all(
                1,
                ft.Colors.GREEN if is_installed else ft.Colors.OUTLINE,
            ),
        )

    def _handle_install(self, tool_name: str) -> None:
        self._installing_tool = tool_name
        self._build_ui()
        if self._on_install:
            self._on_install(tool_name)

    def _handle_dismiss(self, e: ft.ControlEvent | None = None) -> None:
        if self._on_dismiss:
            self._on_dismiss()

    def _handle_recheck(self, e: ft.ControlEvent | None = None) -> None:
        if self._on_recheck:
            self._on_recheck()

    def refresh(self, check_result=None) -> None:
        """Update the dialog after an install attempt or recheck."""
        self._installing_tool = None
        self._build_ui()
