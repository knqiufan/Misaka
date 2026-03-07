"""Image block component for rendering images in messages.

Supports local files, base64 data URLs, and remote URLs.
Provides click-to-view-fullsize functionality.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from misaka.db.models import MessageContentBlock

_MAX_INLINE_WIDTH = 400
_MAX_INLINE_HEIGHT = 300


class ImageBlock(ft.Container):
    """Renders an image block within a message.

    Supports:
    - Local file paths (file:// or absolute paths)
    - Base64 data URLs
    - Remote URLs (http:// or https://)
    """

    def __init__(
        self,
        block: MessageContentBlock,
        on_click: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._block = block
        self._on_click = on_click
        self._image_src: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the image block UI."""
        src = self._resolve_image_source()
        if not src:
            self._build_error_ui()
            return

        self._image_src = src

        # Create image control
        image = ft.Image(
            src=src,
            width=_MAX_INLINE_WIDTH,
            height=_MAX_INLINE_HEIGHT,
            fit=ft.BoxFit.CONTAIN,
            border_radius=8,
            gapless_playback=True,
        )

        # Wrap in clickable container
        self.content = ft.Container(
            content=image,
            on_click=self._handle_click,
            ink=True,
            border_radius=8,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        self.padding = ft.Padding.symmetric(vertical=4)

    def _resolve_image_source(self) -> str | None:
        """Resolve the image source to a format Flet can display."""
        source_type = self._block.source_type
        file_path = self._block.file_path
        url = self._block.url
        base64_data = self._block.base64_data
        media_type = self._block.media_type or "image/png"

        # Local file path
        if source_type == "file" and file_path:
            if os.path.exists(file_path):
                # Flet can display local file paths directly
                return file_path
            return None

        # Remote URL
        if source_type == "url" and url:
            return url

        # Base64 data (from DB or inline)
        if source_type == "base64" and base64_data:
            return f"data:{media_type};base64,{base64_data}"

        # Legacy: check if file_path is actually a base64 string
        if file_path and file_path.startswith("data:"):
            return file_path

        # Check if there's inline base64 data
        if base64_data:
            return f"data:{media_type};base64,{base64_data}"

        return None

    def _build_error_ui(self) -> None:
        """Build UI for when image cannot be loaded."""
        self.content = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.BROKEN_IMAGE_ROUNDED, size=20, opacity=0.5),
                    ft.Text(
                        self._block.alt_text or "Image unavailable",
                        size=12,
                        opacity=0.5,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=8,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        )

    def _handle_click(self, e: ft.ControlEvent) -> None:
        """Handle click to view full-size image."""
        if self._on_click and self._image_src:
            self._on_click(self._image_src)

    def get_image_source(self) -> str | None:
        """Return the resolved image source for full-size viewing."""
        return self._image_src
