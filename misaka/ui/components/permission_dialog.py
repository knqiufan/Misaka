"""Permission dialog component.

Modal dialog for approving or denying tool permission requests
from the Claude SDK. Displays tool name, input details, and
suggestion options.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.state import AppState, PermissionRequest


class PermissionDialog(ft.Container):
    """Permission approval dialog overlay.

    Displayed as a modal when the Claude SDK requests permission
    to use a tool. Connects to AppState.pending_permission and
    resolves the permission future on user action.
    """

    def __init__(
        self,
        state: AppState,
        on_allow: Callable[[], None] | None = None,
        on_deny: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self._on_allow = on_allow
        self._on_deny = on_deny
        self._build_ui()

    def _build_ui(self) -> None:
        request = self.state.pending_permission
        if not request:
            self.visible = False
            self.content = ft.Container()
            return

        self.visible = True

        # Format the input for display
        input_display = ""
        if request.tool_input:
            try:
                input_display = json.dumps(
                    request.tool_input, indent=2, ensure_ascii=False
                )
            except (TypeError, ValueError):
                input_display = str(request.tool_input)

        # Truncate long input
        if len(input_display) > 1000:
            input_display = input_display[:1000] + "\n... (truncated)"

        # Build the dialog content
        dialog_content = ft.Column(
            controls=[
                # Icon and title
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.SECURITY,
                            size=24,
                            color=ft.Colors.ORANGE,
                        ),
                        ft.Text(
                            t("permission.title"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Divider(height=1),
                # Tool info
                ft.Text(
                    t("permission.tool_request", tool_name=request.tool_name),
                    size=14,
                    weight=ft.FontWeight.W_500,
                ),
                # Input details
                ft.Container(
                    content=ft.Text(
                        input_display,
                        font_family="Consolas, Monaco, monospace",
                        size=12,
                        selectable=True,
                        no_wrap=False,
                    ),
                    padding=12,
                    border_radius=6,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                    max_height=300,
                ),
            ],
            spacing=12,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        )

        # Suggestion text if available
        if request.suggestions:
            for suggestion in request.suggestions:
                if isinstance(suggestion, dict):
                    desc = suggestion.get("description", str(suggestion))
                    dialog_content.controls.append(
                        ft.Text(desc, size=12, italic=True, opacity=0.7)
                    )

        # Action buttons
        actions = ft.Row(
            controls=[
                ft.Container(expand=True),
                ft.OutlinedButton(
                    content=t("permission.deny"),
                    icon=ft.Icons.CLOSE,
                    on_click=self._handle_deny,
                    style=ft.ButtonStyle(
                        color=ft.Colors.ERROR,
                    ),
                ),
                ft.Button(
                    content=t("permission.allow"),
                    icon=ft.Icons.CHECK,
                    on_click=self._handle_allow,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.PRIMARY,
                        color=ft.Colors.ON_PRIMARY,
                    ),
                ),
            ],
            spacing=12,
        )

        # Modal overlay
        self.content = ft.Container(
            content=ft.Container(
                content=ft.Column(
                    controls=[dialog_content, actions],
                    spacing=16,
                ),
                width=500,
                padding=24,
                border_radius=12,
                bgcolor=ft.Colors.SURFACE,
                shadow=ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=20,
                    color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
                ),
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK),
        )
        self.expand = True

    def _handle_allow(self, e: ft.ControlEvent) -> None:
        if self._on_allow:
            self._on_allow()

    def _handle_deny(self, e: ft.ControlEvent) -> None:
        if self._on_deny:
            self._on_deny()

    def refresh(self) -> None:
        """Rebuild the dialog based on current permission state."""
        self._build_ui()
