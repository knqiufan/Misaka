"""Custom floating context menu component.

Renders a modern right-click context menu via ``page.overlay``, matching
the Misaka design system (rounded corners, soft shadow, hover highlight).
Use ``FloatingContextMenu.show()`` to open and ``FloatingContextMenu.dismiss()``
to close. Only one menu is visible at a time globally.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class ContextMenuItem:
    """Descriptor for one row inside the floating context menu."""

    icon: str
    label: str
    on_click: Callable[[], None]
    icon_color: str | None = None


class FloatingContextMenu:
    """Manages a single floating context menu rendered via ``page.overlay``.

    Opening a new menu automatically dismisses the previous one.
    A transparent full-screen backdrop closes the menu on any outside click.
    """

    def __init__(self) -> None:
        self._overlay_stack: ft.Stack | None = None
        self._page: ft.Page | None = None

    def show(
        self,
        page: ft.Page,
        *,
        global_x: float,
        global_y: float,
        items: list[ContextMenuItem],
    ) -> None:
        """Open the menu at (*global_x*, *global_y*) with the given items."""
        self.dismiss()
        self._page = page

        menu_rows = [self._build_item(item) for item in items]

        menu_panel = ft.Container(
            content=ft.Column(controls=menu_rows, spacing=0, tight=True),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=14,
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
            ),
            padding=ft.Padding.symmetric(vertical=0),
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=-2,
                offset=ft.Offset(0, 6),
                color=ft.Colors.with_opacity(0.16, ft.Colors.BLACK),
            ),
            width=100,
            left=global_x,
            top=global_y,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        backdrop = ft.GestureDetector(
            content=ft.Container(bgcolor=ft.Colors.TRANSPARENT),
            expand=True,
            on_tap=lambda _: self.dismiss(),
        )

        self._overlay_stack = ft.Stack(
            controls=[backdrop, menu_panel],
            expand=True,
        )

        page.overlay.append(self._overlay_stack)
        page.update()

    def dismiss(self) -> None:
        """Close the menu and remove overlay controls."""
        if not self._page or not self._overlay_stack:
            return
        if self._overlay_stack in self._page.overlay:
            self._page.overlay.remove(self._overlay_stack)
            with contextlib.suppress(Exception):
                self._page.update()
        self._overlay_stack = None
        self._page = None

    def _build_item(self, item: ContextMenuItem) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(item.label, size=12, weight=ft.FontWeight.W_500),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=9),
            border_radius=8,
            ink=True,
            on_click=lambda _: item.on_click(),
            on_hover=self._on_item_hover,
        )

    @staticmethod
    def _on_item_hover(e: ft.HoverEvent) -> None:
        ctrl: ft.Container = e.control
        ctrl.bgcolor = (
            ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
            if e.data == "true"
            else ft.Colors.TRANSPARENT
        )
        ctrl.update()


shared_context_menu = FloatingContextMenu()
