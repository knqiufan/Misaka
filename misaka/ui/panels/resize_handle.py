"""Resize handle component.

Draggable handle between panels for adjusting panel widths.
Uses GestureDetector to track horizontal drag events.

Reports global X position for visual feedback during drag,
and applies final width on drag end for optimal performance.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft


class ResizeHandle(ft.GestureDetector):
    """Draggable resize handle between panels.

    The handle is a thin vertical bar that changes cursor on hover
    and reports drag position via callbacks.

    During drag, reports global X position for visual indicator.
    On drag end, triggers callback to apply final panel width.
    """

    def __init__(
        self,
        on_drag_start: Callable[[], None] | None = None,
        on_drag: Callable[[float], None] | None = None,
        on_drag_end: Callable[[], None] | None = None,
    ) -> None:
        self._on_drag_start = on_drag_start
        self._on_drag = on_drag
        self._on_drag_end = on_drag_end

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
            on_horizontal_drag_start=self._handle_drag_start,
            on_horizontal_drag_update=self._handle_drag,
            on_horizontal_drag_end=self._handle_drag_end,
            on_enter=self._on_enter,
            on_exit=self._on_exit,
            expand_loose=True,
        )

    def _handle_drag_start(self, e: ft.DragStartEvent) -> None:
        """Notify drag start to show visual indicator."""
        if self._on_drag_start:
            self._on_drag_start()

    def _handle_drag(self, e: ft.DragUpdateEvent) -> None:
        """Report global X position for visual feedback."""
        if self._on_drag:
            self._on_drag(e.global_position.x)

    def _handle_drag_end(self, e: ft.DragEndEvent) -> None:
        """Notify drag end to apply final width."""
        if self._on_drag_end:
            self._on_drag_end()

    def _on_enter(self, e: ft.HoverEvent) -> None:
        self._bar.bgcolor = ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY)
        self._bar.update()

    def _on_exit(self, e: ft.HoverEvent) -> None:
        self._bar.bgcolor = ft.Colors.TRANSPARENT
        self._bar.update()
