"""Connection status indicator component.

Shows the current connection state to the Claude SDK,
including model name and streaming status.
"""

from __future__ import annotations

import flet as ft

from misaka.i18n import t


class ConnectionStatus(ft.Row):
    """Small status indicator showing SDK connection state."""

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
            color = "#f59e0b"
        elif self._connected:
            color = "#10b981"
        else:
            color = "#6b7280"

        label = self._model or (
            t("chat.connected") if self._connected else t("chat.disconnected")
        )

        self._dot = ft.Container(
            width=6,
            height=6,
            border_radius=3,
            bgcolor=color,
        )
        self._label = ft.Text(label, size=11, opacity=0.6)
        self.controls = [self._dot, self._label]

    def set_status(
        self,
        *,
        connected: bool | None = None,
        model: str | None = None,
        is_streaming: bool | None = None,
    ) -> None:
        """Update the connection status display."""
        if connected is not None:
            self._connected = connected
        if model is not None:
            self._model = model
        if is_streaming is not None:
            self._is_streaming = is_streaming
        self._build_ui()
