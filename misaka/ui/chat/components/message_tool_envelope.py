"""Outer collapsible wrapper for many tool calls in one assistant message."""

from __future__ import annotations

import contextlib
from collections import Counter

import flet as ft

from misaka.i18n import t


class MessageToolEnvelope(ft.Container):
    """Collapse an entire tool region behind one summary row."""

    def __init__(
        self,
        tool_controls: list[ft.Control],
        *,
        tool_count: int,
        type_summary: str,
    ) -> None:
        super().__init__()
        self._tool_controls = tool_controls
        self._tool_count = tool_count
        self._type_summary = type_summary
        self._expanded = False
        self._children_host: ft.Column | None = None
        self._chevron: ft.Icon | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self._chevron = ft.Icon(
            ft.Icons.CHEVRON_RIGHT_ROUNDED,
            size=14,
            opacity=0.4,
        )
        summary = t("chat.message_tools_summary").format(count=self._tool_count)
        summary_row = ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.LAYERS_OUTLINED,
                    size=16,
                    color=ft.Colors.PRIMARY,
                    opacity=0.6,
                ),
                ft.Text(summary, size=12, weight=ft.FontWeight.W_600),
                ft.Text(
                    self._type_summary,
                    size=11,
                    opacity=0.4,
                    expand=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                self._chevron,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._children_host = ft.Column(spacing=8, tight=True, visible=False)
        self._host_wrapper = ft.Container(
            content=self._children_host,
            padding=ft.Padding.only(left=8, top=6, bottom=4),
            visible=False,
        )
        self.content = ft.Column(
            controls=[
                ft.Container(
                    content=summary_row,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                    on_click=self._toggle,
                    ink=True,
                    border_radius=8,
                ),
                self._host_wrapper,
            ],
            spacing=0,
            tight=True,
        )
        self.border_radius = 10
        self.margin = ft.Margin.only(top=2, bottom=2)
        self.bgcolor = ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY)
        self.border = ft.Border.all(
            1, ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
        )

    def _toggle(self, e: ft.ControlEvent) -> None:
        self._expanded = not self._expanded
        if self._chevron:
            self._chevron.name = (
                ft.Icons.EXPAND_MORE_ROUNDED if self._expanded
                else ft.Icons.CHEVRON_RIGHT_ROUNDED
            )
            with contextlib.suppress(Exception):
                self._chevron.update()
        if self._host_wrapper and self._children_host:
            if self._expanded and not self._children_host.controls:
                self._children_host.controls = list(self._tool_controls)
            self._host_wrapper.visible = self._expanded
            self._children_host.visible = self._expanded
            with contextlib.suppress(Exception):
                self._host_wrapper.update()


def compute_tool_type_summary(tool_names: list[str]) -> str:
    """Build summary like 'Glob x5, Bash x1'."""
    counter = Counter(tool_names)
    parts = [f"{name} x{count}" for name, count in counter.most_common()]
    return ", ".join(parts)
