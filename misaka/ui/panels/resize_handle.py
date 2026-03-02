"""Resize handle component.

Draggable handle between panels for adjusting panel widths.
Uses GestureDetector to track horizontal drag events.
"""

from __future__ import annotations

from typing import Callable

import flet as ft


class ResizeHandle(ft.GestureDetector):
    """Draggable resize handle between panels.

    The handle is a thin vertical bar that changes cursor on hover
    and reports drag deltas via the ``on_resize`` callback.
    """

    def __init__(
        self,
        on_resize: Callable[[float], None] | None = None,
    ) -> None:
        self._on_resize = on_resize
        self._bar = ft.Container(
            width=4,
            bgcolor=ft.Colors.TRANSPARENT,
            border_radius=2,
        )
        super().__init__(
            content=ft.Container(
                content=self._bar,
                width=8,
                alignment=ft.Alignment.CENTER,
                expand=True,
            ),
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            on_horizontal_drag_update=self._handle_drag,
            on_enter=self._on_enter,
            on_exit=self._on_exit,
            expand_loose=True,
        )

    def _handle_drag(self, e: ft.DragUpdateEvent) -> None:
        if self._on_resize and e.local_delta is not None:
            self._on_resize(e.local_delta.x)

    def _on_enter(self, e: ft.HoverEvent) -> None:
        self._bar.bgcolor = ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY)
        self._bar.update()

    def _on_exit(self, e: ft.HoverEvent) -> None:
        self._bar.bgcolor = ft.Colors.TRANSPARENT
        self._bar.update()
