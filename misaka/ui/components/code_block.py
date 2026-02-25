"""Code block component.

Renders syntax-highlighted code with a language label and copy button.
Uses Flet Markdown with code fence for rendering.
"""

from __future__ import annotations

import asyncio

import flet as ft


class CodeBlock(ft.Container):
    """Syntax-highlighted code display with copy button and language label."""

    def __init__(self, code: str, language: str = "plaintext") -> None:
        super().__init__()
        self._code = code
        self._language = language
        self._build_ui()

    def _build_ui(self) -> None:
        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        self._language,
                        size=11,
                        weight=ft.FontWeight.W_500,
                        opacity=0.6,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CONTENT_COPY,
                        icon_size=14,
                        tooltip="Copy code",
                        on_click=self._copy,
                        style=ft.ButtonStyle(padding=4),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.only(left=12, right=4, top=4, bottom=0),
        )

        code_content = ft.Container(
            content=ft.Text(
                self._code,
                font_family="Cascadia Code, JetBrains Mono, Consolas, monospace",
                size=12,
                selectable=True,
                no_wrap=False,
            ),
            padding=ft.Padding.only(left=12, right=12, top=4, bottom=10),
        )

        self.content = ft.Column(
            controls=[header, code_content],
            spacing=0,
        )
        self.border_radius = 6
        self.margin = ft.Margin.only(top=4, bottom=4)
        self.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH
        self.border = ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE))

    async def _copy(self, e: ft.ControlEvent) -> None:
        """Copy code to clipboard."""
        if e.page:
            e.page.set_clipboard(self._code)
            # Brief visual feedback
            if e.control and hasattr(e.control, 'icon'):
                e.control.icon = ft.Icons.CHECK
                e.control.update()

                await asyncio.sleep(1.5)

                e.control.icon = ft.Icons.CONTENT_COPY
                try:
                    e.control.update()
                except Exception:
                    pass
