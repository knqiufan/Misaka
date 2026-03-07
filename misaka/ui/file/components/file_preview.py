"""File preview component.

Displays file content with syntax highlighting info,
line count, copy button, and scrollable code display.
"""

from __future__ import annotations

import flet as ft

from misaka.db.models import FilePreview as FilePreviewModel
from misaka.i18n import t
from misaka.ui.common.theme import MONO_FONT_FAMILY, make_icon_button


class FilePreview(ft.Column):
    """Syntax-highlighted file content viewer."""

    def __init__(
        self,
        preview: FilePreviewModel | None = None,
        on_close: None | object = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self._preview = preview
        self._on_close = on_close
        self._build_ui()

    def _build_ui(self) -> None:
        if not self._preview:
            self.controls = [
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.PREVIEW, size=36, opacity=0.3),
                            ft.Text(
                                t("right_panel.select_file_preview"),
                                italic=True,
                                size=13,
                                opacity=0.5,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                )
            ]
            return

        # Header with file info
        # Extract just the filename from the path
        filename = self._preview.path.replace("\\", "/").split("/")[-1]

        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DESCRIPTION, size=16),
                    ft.Text(
                        filename,
                        size=13,
                        weight=ft.FontWeight.W_500,
                        expand=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        self._preview.language,
                        size=11,
                        italic=True,
                        opacity=0.6,
                    ),
                    ft.Text(
                        f"{self._preview.line_count} lines",
                        size=11,
                        opacity=0.5,
                    ),
                    make_icon_button(
                        ft.Icons.CONTENT_COPY,
                        tooltip=t("right_panel.copy_content"),
                        on_click=self._copy_content,
                        icon_size=16,
                    ),
                    *(
                        [
                            make_icon_button(
                                ft.Icons.CLOSE,
                                tooltip=t("right_panel.close_preview"),
                                on_click=self._on_close,
                                icon_size=16,
                            ),
                        ]
                        if self._on_close
                        else []
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        )

        # Path display
        path_bar = ft.Container(
            content=ft.Text(
                self._preview.path,
                size=10,
                opacity=0.5,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                selectable=True,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        )

        # Code content
        code_view = ft.Container(
            content=ft.Text(
                self._preview.content,
                font_family=MONO_FONT_FAMILY,
                size=12,
                selectable=True,
                no_wrap=False,
            ),
            expand=True,
            padding=12,
        )

        # Wrap in a scrollable container
        scrollable = ft.Column(
            controls=[code_view],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        self.controls = [header, path_bar, ft.Divider(height=1), scrollable]

    def set_preview(self, preview: FilePreviewModel | None) -> None:
        """Update the displayed file preview."""
        self._preview = preview
        self._build_ui()

    async def _copy_content(self, e: ft.ControlEvent) -> None:
        """Copy file content to clipboard."""
        if e.page and self._preview:
            await ft.Clipboard().set(self._preview.content)
