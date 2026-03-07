"""Code block component.

Renders syntax-highlighted code with a language label and copy button.
Modern dark-panel design inspired by GitHub Dark / One Dark Pro themes.
"""

from __future__ import annotations

import asyncio
import contextlib

import flet as ft

from misaka.ui.common.theme import MONO_FONT_FAMILY, make_icon_button


class CodeBlock(ft.Container):
    """Syntax-highlighted code display with copy button and language label."""

    def __init__(self, code: str, language: str = "plaintext") -> None:
        super().__init__()
        self._code = code
        self._language = language
        self._build_ui()

    def _build_ui(self) -> None:
        lang_badge = ft.Container(
            content=ft.Text(
                self._language,
                size=10,
                weight=ft.FontWeight.W_600,
                opacity=0.5,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=1),
        )

        copy_btn = make_icon_button(
            ft.Icons.CONTENT_COPY_ROUNDED,
            tooltip="Copy code",
            on_click=self._copy,
            icon_size=13,
        )

        header = ft.Container(
            content=ft.Row(
                controls=[lang_badge, copy_btn],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.only(left=14, right=4, top=6, bottom=0),
        )

        code_content = ft.Container(
            content=ft.Text(
                self._code,
                font_family=MONO_FONT_FAMILY,
                size=12,
                selectable=True,
                no_wrap=False,
            ),
            padding=ft.Padding.only(left=14, right=14, top=4, bottom=14),
        )

        self.content = ft.Column(
            controls=[header, code_content],
            spacing=0,
        )
        self.border_radius = 10
        self.margin = ft.Margin.only(top=4, bottom=4)
        self.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH
        self.border = ft.Border.all(
            1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        )
        self.shadow = ft.BoxShadow(
            blur_radius=6,
            spread_radius=-2,
            color=ft.Colors.with_opacity(0.03, ft.Colors.BLACK),
            offset=ft.Offset(0, 1),
        )

    async def _copy(self, e: ft.ControlEvent) -> None:
        """Copy code to clipboard with check-mark feedback."""
        if e.page:
            await ft.Clipboard().set(self._code)
            if e.control and hasattr(e.control, 'icon'):
                e.control.icon = ft.Icons.CHECK_ROUNDED
                e.control.icon_color = ft.Colors.GREEN
                e.control.update()

                await asyncio.sleep(1.5)

                e.control.icon = ft.Icons.CONTENT_COPY_ROUNDED
                e.control.icon_color = None
                with contextlib.suppress(Exception):
                    e.control.update()
