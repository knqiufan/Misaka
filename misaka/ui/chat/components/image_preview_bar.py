"""Image preview bar component.

A horizontal scrollable row of image thumbnails displayed above the input field.
Each thumbnail has an X button overlay for deletion and can be clicked to view
the full-size image in an overlay.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.db.models import PendingImage

if TYPE_CHECKING:
    pass

THUMBNAIL_SIZE = 80


class ImageThumbnail(ft.Container):
    """A single image thumbnail with delete button overlay."""

    def __init__(
        self,
        pending_image: PendingImage,
        on_delete: Callable[[str], None] | None = None,
        on_click: Callable[[PendingImage], None] | None = None,
    ) -> None:
        super().__init__()
        self._pending = pending_image
        self._on_delete = on_delete
        self._on_click = on_click

        # Convert thumbnail bytes to base64 for display
        thumb_base64 = base64.b64encode(pending_image.thumbnail).decode("utf-8")
        thumb_src = f"data:image/jpeg;base64,{thumb_base64}"

        # Delete button overlay
        delete_btn = ft.Container(
            content=ft.Icon(
                ft.Icons.CLOSE_ROUNDED,
                size=14,
                color=ft.Colors.WHITE,
            ),
            bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
            border_radius=10,
            padding=2,
            on_click=self._handle_delete,
            ink=True,
        )

        # Image with rounded corners
        image = ft.Image(
            src=thumb_src,
            width=THUMBNAIL_SIZE,
            height=THUMBNAIL_SIZE,
            fit=ft.BoxFit.COVER,
            border_radius=8,
        )

        # Stack: image with delete button in top-right corner
        self.content = ft.Stack(
            controls=[
                ft.Container(
                    content=image,
                    on_click=self._handle_click,
                    ink=True,
                    border_radius=8,
                ),
                ft.Container(
                    content=delete_btn,
                    alignment=ft.Alignment(1.0, -1.0),  # top_right
                    padding=4,
                ),
            ],
            width=THUMBNAIL_SIZE,
            height=THUMBNAIL_SIZE,
        )

        self.width = THUMBNAIL_SIZE
        self.height = THUMBNAIL_SIZE
        self.border_radius = 8
        self.clip_behavior = ft.ClipBehavior.ANTI_ALIAS

    def _handle_delete(self, e: ft.ControlEvent) -> None:
        """Handle delete button click."""
        if self._on_delete:
            self._on_delete(self._pending.id)

    def _handle_click(self, e: ft.ControlEvent) -> None:
        """Handle thumbnail click to view full-size."""
        if self._on_click:
            self._on_click(self._pending)


class ImagePreviewBar(ft.Container):
    """A horizontal scrollable bar of image thumbnails above the input.

    Features:
    - 80x80 thumbnails in a single horizontal row
    - X button overlay on each thumbnail for deletion
    - Click thumbnail to open full-size viewer
    - Horizontal scroll when more than ~5 images
    """

    def __init__(
        self,
        on_delete_image: Callable[[str], None] | None = None,
        on_view_image: Callable[[PendingImage], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_delete_image = on_delete_image
        self._on_view_image = on_view_image
        self._pending_images: list[PendingImage] = []
        self._thumbnail_row: ft.Row | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the preview bar UI."""
        self._thumbnail_row = ft.Row(
            controls=[],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            height=THUMBNAIL_SIZE + 8,  # Extra space for potential overflow
        )

        self.content = self._thumbnail_row
        self.padding = ft.Padding.symmetric(vertical=4)
        self.visible = False  # Hidden when no images

    def update_images(self, images: list[PendingImage]) -> None:
        """Update the displayed images.

        Args:
            images: List of pending images to display.
        """
        self._pending_images = images
        self._render_thumbnails()

    def _render_thumbnails(self) -> None:
        """Re-render all thumbnails."""
        if not self._thumbnail_row:
            return

        if not self._pending_images:
            self.visible = False
            self._thumbnail_row.controls = []
        else:
            self.visible = True
            self._thumbnail_row.controls = [
                ImageThumbnail(
                    pending_image=img,
                    on_delete=self._handle_delete,
                    on_click=self._handle_click,
                )
                for img in self._pending_images
            ]

        try:
            self.update()
        except Exception:
            pass  # Control may not be mounted yet

    def _handle_delete(self, image_id: str) -> None:
        """Handle delete request for an image."""
        if self._on_delete_image:
            self._on_delete_image(image_id)

    def _handle_click(self, pending: PendingImage) -> None:
        """Handle click to view full-size image."""
        if self._on_view_image:
            self._on_view_image(pending)

    def clear(self) -> None:
        """Clear all images."""
        self._pending_images = []
        self._render_thumbnails()
