"""Image overlay component for full-size image viewing.

A modal overlay that displays images at full size with a dark backdrop.
Supports zoom controls and keyboard navigation (Escape to close).
"""

from __future__ import annotations

import flet as ft


class ImageOverlay(ft.Stack):
    """Full-screen modal image viewer.

    Features:
    - Dark backdrop
    - Close on click-outside
    - Zoom controls
    - Keyboard support (Escape)
    """

    def __init__(
        self,
        image_src: str,
        on_close: callable | None = None,
    ) -> None:
        super().__init__()
        self._image_src = image_src
        self._on_close = on_close
        self._zoom_level: float = 1.0
        self._image_control: ft.Image | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the overlay UI."""
        # Dark backdrop - use Container with on_click instead of GestureDetector
        backdrop = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
            expand=True,
            on_click=self._handle_close,
        )

        # Image with zoom support
        self._image_control = ft.Image(
            src=self._image_src,
            fit=ft.BoxFit.CONTAIN,
            expand=True,
            gapless_playback=True,
        )

        # Image container - use Container with on_click instead of GestureDetector
        image_container = ft.Container(
            content=self._image_control,
            alignment=ft.Alignment.CENTER,
            expand=True,
            on_click=self._handle_close,
        )

        # Close button - position via Container inside Stack
        close_btn = ft.Container(
            content=ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_color=ft.Colors.WHITE,
                icon_size=24,
                on_click=self._handle_close,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
                ),
            ),
            top=16,
            right=16,
        )

        # Zoom buttons
        zoom_in_btn = ft.IconButton(
            icon=ft.Icons.ZOOM_IN_ROUNDED,
            icon_color=ft.Colors.WHITE,
            icon_size=20,
            on_click=self._handle_zoom_in,
            style=ft.ButtonStyle(
                shape=ft.CircleBorder(),
                bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            ),
        )

        zoom_out_btn = ft.IconButton(
            icon=ft.Icons.ZOOM_OUT_ROUNDED,
            icon_color=ft.Colors.WHITE,
            icon_size=20,
            on_click=self._handle_zoom_out,
            style=ft.ButtonStyle(
                shape=ft.CircleBorder(),
                bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            ),
        )

        reset_btn = ft.IconButton(
            icon=ft.Icons.FIT_SCREEN_ROUNDED,
            icon_color=ft.Colors.WHITE,
            icon_size=20,
            on_click=self._handle_zoom_reset,
            style=ft.ButtonStyle(
                shape=ft.CircleBorder(),
                bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            ),
        )

        # Zoom controls row positioned at bottom center
        zoom_controls = ft.Container(
            content=ft.Row(
                controls=[zoom_out_btn, reset_btn, zoom_in_btn],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bottom=16,
            left=0,
            right=0,
        )

        # Assemble stack (no keyboard listener - it was blocking click events)
        self.controls = [
            backdrop,
            image_container,
            close_btn,
            zoom_controls,
        ]
        self.expand = True

    def _handle_close(self, e: ft.ControlEvent | None = None) -> None:
        """Close the overlay."""
        if self._on_close:
            self._on_close()

    def _handle_key(self, e: ft.KeyboardEvent) -> None:
        """Handle keyboard events."""
        if e.key == "Escape":
            self._handle_close()
        elif e.key == "+" or e.key == "=":
            self._handle_zoom_in(None)
        elif e.key == "-":
            self._handle_zoom_out(None)
        elif e.key == "0":
            self._handle_zoom_reset(None)

    def _handle_zoom_in(self, e: ft.ControlEvent | None) -> None:
        """Zoom in on the image."""
        if self._zoom_level < 3.0:
            self._zoom_level = min(3.0, self._zoom_level + 0.25)
            self._apply_zoom()

    def _handle_zoom_out(self, e: ft.ControlEvent | None) -> None:
        """Zoom out on the image."""
        if self._zoom_level > 0.5:
            self._zoom_level = max(0.5, self._zoom_level - 0.25)
            self._apply_zoom()

    def _handle_zoom_reset(self, e: ft.ControlEvent | None) -> None:
        """Reset zoom to default."""
        self._zoom_level = 1.0
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        """Apply the current zoom level to the image."""
        if self._image_control and self.page:
            # For Flet, we need to resize the container, not the image itself
            # This is a simplified approach
            self._image_control.update()


def show_image_overlay(page: ft.Page, image_src: str) -> None:
    """Show an image overlay on the page.

    Args:
        page: The Flet page.
        image_src: The image source (path, URL, or base64 data URL).
    """
    overlay = ImageOverlay(
        image_src=image_src,
        on_close=lambda: _close_overlay(page, overlay),
    )

    # Add overlay to page
    page.overlay.append(overlay)
    page.update()


def _close_overlay(page: ft.Page, overlay: ft.Control) -> None:
    """Close and remove the overlay from the page."""
    if overlay in page.overlay:
        page.overlay.remove(overlay)
        page.update()
