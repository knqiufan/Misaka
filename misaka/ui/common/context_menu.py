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
    """

    def __init__(self) -> None:
        self._menu_overlay: ft.Container | None = None
        self._page: ft.Page | None = None
        self._last_items: list[ContextMenuItem] | None = None
        self._last_width: int | None = None

    def _on_menu_secondary_tap(self, e: ft.TapEvent) -> None:
        """On right-click over menu: reopen it at the new pointer position."""
        page = self._page
        items = self._last_items
        if not page or not items:
            self.dismiss()
            return
        pos = e.global_position
        width = self._last_width
        self.dismiss()
        self.show(
            page,
            global_x=pos.x,
            global_y=pos.y,
            items=items,
            width=width,
        )

    def show(
        self,
        page: ft.Page,
        *,
        global_x: float,
        global_y: float,
        items: list[ContextMenuItem],
        width: int | None = None,
    ) -> None:
        """Open the menu at (*global_x*, *global_y*) with the given items."""
        self.dismiss()
        self._page = page
        self._last_items = items
        menu_width = width if width is not None else 200
        self._last_width = menu_width

        menu_rows = [self._build_item(item) for item in items]

        menu_panel_inner = ft.Container(
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
            width=menu_width,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        # Container with left/top can be placed directly in page.overlay
        menu_panel = ft.Container(
            content=ft.GestureDetector(
                content=menu_panel_inner,
                on_secondary_tap_down=self._on_menu_secondary_tap,
            ),
            left=global_x,
            top=global_y,
        )

        self._menu_overlay = menu_panel
        page.overlay.append(menu_panel)
        page.update()

    def dismiss(self) -> None:
        """Close the menu and remove overlay controls."""
        if not self._page or not self._menu_overlay:
            return
        if self._menu_overlay in self._page.overlay:
            self._page.overlay.remove(self._menu_overlay)
            with contextlib.suppress(Exception):
                self._page.update()
        self._menu_overlay = None
        self._page = None
        self._last_items = None

    def _build_item(self, item: ContextMenuItem) -> ft.Control:
        row_controls: list[ft.Control] = []
        if item.icon:
            row_controls.append(
                ft.Icon(
                    item.icon,
                    size=18,
                    color=item.icon_color or ft.Colors.ON_SURFACE_VARIANT,
                ),
            )
        row_controls.append(
            ft.Text(item.label, size=12, weight=ft.FontWeight.W_500),
        )
        return ft.Container(
            content=ft.Row(
                controls=row_controls,
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
