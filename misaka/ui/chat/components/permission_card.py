"""Inline permission card component.

Renders a permission request inline in the chat message stream,
replacing the modal PermissionDialog overlay.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    MONO_FONT_FAMILY,
    RADIUS_LG,
    WARNING_AMBER,
    make_divider,
)

if TYPE_CHECKING:
    from misaka.state import PermissionRequest


class PermissionCard(ft.Container):
    """Inline card that displays a pending tool permission request.

    Shows the tool name, a JSON preview of the input, and three buttons:
    Allow, Allow & Don't Ask Again, and Deny.
    """

    def __init__(
        self,
        permission: PermissionRequest,
        on_allow: Callable[[], None],
        on_allow_always: Callable[[], None],
        on_deny: Callable[[], None],
    ) -> None:
        super().__init__()
        self._permission = permission
        self._on_allow = on_allow
        self._on_allow_always = on_allow_always
        self._on_deny = on_deny
        self._build_ui()

    def _build_ui(self) -> None:
        req = self._permission

        # Format input JSON for display
        input_display = ""
        if req.tool_input:
            try:
                input_display = json.dumps(req.tool_input, indent=2, ensure_ascii=False)
            except (TypeError, ValueError):
                input_display = str(req.tool_input)

        if len(input_display) > 800:
            input_display = input_display[:800] + "\n... (truncated)"

        header_row = ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.LOCK_OUTLINE_ROUNDED,
                    size=18,
                    color=WARNING_AMBER,
                ),
                ft.Text(
                    t("permission.title"),
                    size=14,
                    weight=ft.FontWeight.W_600,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        tool_label = ft.Text(
            t("permission.tool_request", tool_name=req.tool_name),
            size=13,
            weight=ft.FontWeight.W_500,
        )

        input_preview = ft.Container(
            content=ft.ListView(
                controls=[
                    ft.Text(
                        input_display,
                        font_family=MONO_FONT_FAMILY,
                        size=11,
                        selectable=True,
                        no_wrap=False,
                    ),
                ],
                auto_scroll=False,
                padding=0,
            ),
            padding=10,
            border_radius=8,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            max_height=160,
        )

        action_row = ft.Row(
            controls=[
                ft.OutlinedButton(
                    t("permission.deny"),
                    icon=ft.Icons.CLOSE_ROUNDED,
                    on_click=lambda e: self._on_deny(),
                    style=ft.ButtonStyle(
                        color=ft.Colors.ERROR,
                        side=ft.BorderSide(1, ft.Colors.with_opacity(0.4, ft.Colors.ERROR)),
                    ),
                ),
                ft.OutlinedButton(
                    t("permission.allow"),
                    icon=ft.Icons.CHECK_ROUNDED,
                    on_click=lambda e: self._on_allow(),
                ),
                ft.OutlinedButton(
                    t("permission.allow_always"),
                    icon=ft.Icons.DONE_ALL_ROUNDED,
                    on_click=lambda e: self._on_allow_always(),
                ),
            ],
            spacing=8,
            wrap=True,
        )

        self.content = ft.Column(
            controls=[
                header_row,
                make_divider(),
                tool_label,
                input_preview,
                action_row,
            ],
            spacing=10,
            tight=True,
        )
        self.padding = ft.Padding.symmetric(horizontal=16, vertical=12)
        self.border = ft.Border.all(1, ft.Colors.with_opacity(0.15, WARNING_AMBER))
        self.border_radius = 8
        self.bgcolor = ft.Colors.with_opacity(0.04, WARNING_AMBER)
        self.margin = ft.Margin(left=8, right=8, top=4, bottom=4)
