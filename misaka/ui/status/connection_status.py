"""Connection status indicator component.

Shows the current connection state to the Claude SDK,
including model name and streaming status.
Badge-style pill indicator with semantic colors.
"""

from __future__ import annotations

import contextlib

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import ERROR_RED, SUCCESS_GREEN, WARNING_AMBER

_MODEL_UNSET = object()


class ConnectionStatus(ft.Row):
    """Badge-style status indicator showing SDK connection state."""

    def __init__(
        self,
        connected: bool = False,
        model: str | None = None,
        is_streaming: bool = False,
    ) -> None:
        super().__init__(spacing=6, alignment=ft.MainAxisAlignment.START)
        self._connected = connected
        self._model = model
        self._is_streaming = is_streaming
        self._build_ui()

    def _build_ui(self) -> None:
        if self._is_streaming:
            dot_color = WARNING_AMBER
        elif self._connected:
            dot_color = SUCCESS_GREEN
        else:
            dot_color = ERROR_RED

        label = self._model or (
            t("chat.connected") if self._connected else t("chat.disconnected")
        )

        self._dot = ft.Container(
            width=7,
            height=7,
            border_radius=4,
            bgcolor=dot_color,
            shadow=ft.BoxShadow(
                blur_radius=4,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.4, dot_color),
            ),
        )
        self._label = ft.Text(label, size=11, opacity=0.6)

        badge = ft.Container(
            content=ft.Row(
                controls=[self._dot, self._label],
                spacing=6,
                tight=True,
            ),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        )
        self.controls = [badge]

    def _resolve_label(self) -> str:
        return self._model or (
            t("chat.connected") if self._connected else t("chat.disconnected")
        )

    def _resolve_dot_color(self) -> str:
        if self._is_streaming:
            return WARNING_AMBER
        if self._connected:
            return SUCCESS_GREEN
        return ERROR_RED

    def set_status(
        self,
        *,
        connected: bool | None = None,
        model: str | None | object = _MODEL_UNSET,
        is_streaming: bool | None = None,
    ) -> None:
        """Update the connection status display."""
        if connected is not None:
            self._connected = connected
        if model is not _MODEL_UNSET:
            self._model = model
        if is_streaming is not None:
            self._is_streaming = is_streaming
        dot_color = self._resolve_dot_color()
        self._dot.bgcolor = dot_color
        self._dot.shadow = ft.BoxShadow(
            blur_radius=4,
            spread_radius=0,
            color=ft.Colors.with_opacity(0.4, dot_color),
        )
        self._label.value = self._resolve_label()
        with contextlib.suppress(Exception):
            self.update()
