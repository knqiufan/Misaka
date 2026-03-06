"""Resize handle component.

Draggable handle between panels for adjusting panel widths.
Uses GestureDetector to track horizontal drag events with throttled updates.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import flet as ft


class ResizeHandle(ft.GestureDetector):
    """Draggable resize handle between panels.

    The handle is a thin vertical bar that changes cursor on hover
    and reports drag deltas via the ``on_resize`` callback.

    Drag events are throttled to ~60fps to reduce UI update frequency
    while maintaining responsive feel.
    """

    # Throttle interval: ~60fps = 16ms
    _UPDATE_INTERVAL = 0.016

    def __init__(
        self,
        on_resize: Callable[[float], None] | None = None,
    ) -> None:
        self._on_resize = on_resize
        self._pending_delta = 0.0
        self._last_update_time = 0.0

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
            on_horizontal_drag_end=self._handle_drag_end,
            on_enter=self._on_enter,
            on_exit=self._on_exit,
            expand_loose=True,
        )

    def _handle_drag(self, e: ft.DragUpdateEvent) -> None:
        """Accumulate drag delta and flush if enough time has passed."""
        if e.local_delta is not None:
            self._pending_delta += e.local_delta.x
            self._maybe_flush_delta()

    def _handle_drag_end(self, e: ft.DragEndEvent) -> None:
        """Flush remaining delta when drag ends."""
        self._flush_delta()

    def _maybe_flush_delta(self) -> None:
        """Throttle: only flush if enough time has passed since last update."""
        now = time.monotonic()
        if now - self._last_update_time >= self._UPDATE_INTERVAL:
            self._flush_delta()

    def _flush_delta(self) -> None:
        """Send accumulated delta to callback."""
        if self._pending_delta != 0 and self._on_resize:
            delta = self._pending_delta
            self._pending_delta = 0.0
            self._last_update_time = time.monotonic()
            self._on_resize(delta)

    def _on_enter(self, e: ft.HoverEvent) -> None:
        self._bar.bgcolor = ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY)
        self._bar.update()

    def _on_exit(self, e: ft.HoverEvent) -> None:
        self._bar.bgcolor = ft.Colors.TRANSPARENT
        self._bar.update()
