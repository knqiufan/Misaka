"""Tool group block component.

Renders a collapsed summary when 3+ consecutive tool calls occur,
with lazy-loaded detail views to reduce rendering pressure.
"""

from __future__ import annotations

import contextlib
from collections import Counter
from dataclasses import dataclass

import flet as ft

from misaka.i18n import t
from misaka.ui.chat.components.tool_call_block import ToolCallBlock

_TOOL_ICONS = {
    "Read": ft.Icons.DESCRIPTION_OUTLINED,
    "Write": ft.Icons.EDIT_NOTE_OUTLINED,
    "Edit": ft.Icons.EDIT_OUTLINED,
    "Bash": ft.Icons.TERMINAL_ROUNDED,
    "Glob": ft.Icons.SEARCH_ROUNDED,
    "Grep": ft.Icons.FIND_IN_PAGE_OUTLINED,
    "WebFetch": ft.Icons.LANGUAGE_ROUNDED,
    "WebSearch": ft.Icons.TRAVEL_EXPLORE_ROUNDED,
    "TodoWrite": ft.Icons.CHECKLIST_ROUNDED,
    "Task": ft.Icons.TASK_OUTLINED,
}


@dataclass
class ToolCallInfo:
    """Lightweight tool call data for deferred rendering."""

    name: str
    tool_input: dict | None = None
    result: str | None = None
    is_error: bool = False


class ToolGroupBlock(ft.Container):
    """Collapsed display for consecutive tool calls (3+).

    Shows a summary line with tool counts. On expand, displays
    per-tool-type statistics. Full ToolCallBlock instances are only
    created when user explicitly requests detail view.
    """

    def __init__(self, tools: list[ToolCallInfo]) -> None:
        super().__init__()
        self._tools = tools
        self._expanded = False
        self._detail_loaded = False
        self._detail_column: ft.Column | None = None
        self._stats_column: ft.Column | None = None
        self._chevron: ft.Icon | None = None
        self._summary_text = self._compute_summary()
        self._build_ui()

    def _compute_summary(self) -> str:
        """Compute a compact summary string like 'Read x3, Write x2'."""
        counter = Counter(tool.name for tool in self._tools)
        parts = [f"{name} x{count}" for name, count in counter.most_common()]
        return ", ".join(parts)

    def _count_errors(self) -> int:
        return sum(1 for t in self._tools if t.is_error)

    def _build_ui(self) -> None:
        total = len(self._tools)
        error_count = self._count_errors()

        self._chevron = ft.Icon(
            ft.Icons.EXPAND_MORE_ROUNDED if self._expanded
            else ft.Icons.CHEVRON_RIGHT_ROUNDED,
            size=14,
            opacity=0.4,
        )

        status_text = t("chat.tool_group_summary").format(count=total)
        if error_count > 0:
            status_text += f" ({error_count} " + t("chat.tool_group_errors") + ")"

        summary_row = ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.BUILD_CIRCLE_OUTLINED,
                    size=16,
                    color=ft.Colors.PRIMARY,
                    opacity=0.6,
                ),
                ft.Text(
                    status_text,
                    size=12,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    self._summary_text,
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

        self._stats_column = ft.Column(spacing=4, tight=True, visible=False)
        self._detail_column = ft.Column(spacing=2, tight=True, visible=False)

        expand_container = ft.Container(
            content=ft.Column(
                controls=[self._stats_column, self._detail_column],
                spacing=8,
                tight=True,
            ),
            padding=ft.Padding.only(left=24, right=8, top=6, bottom=8),
            visible=self._expanded,
        )
        self._expand_container = expand_container

        self.content = ft.Column(
            controls=[
                ft.Container(
                    content=summary_row,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                    on_click=self._toggle,
                    ink=True,
                    border_radius=8,
                ),
                expand_container,
            ],
            spacing=0,
            tight=True,
        )
        self.border_radius = 10
        self.margin = ft.Margin.only(top=2, bottom=2)
        self.bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE)
        self.border = ft.Border.all(
            1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        )

    def _toggle(self, e: ft.ControlEvent) -> None:
        """Toggle expanded state, building stats on first expand."""
        self._expanded = not self._expanded

        if self._chevron:
            self._chevron.name = (
                ft.Icons.EXPAND_MORE_ROUNDED if self._expanded
                else ft.Icons.CHEVRON_RIGHT_ROUNDED
            )
            with contextlib.suppress(Exception):
                self._chevron.update()

        if self._expand_container:
            self._expand_container.visible = self._expanded
            if self._expanded and self._stats_column and not self._stats_column.controls:
                self._build_stats()
            with contextlib.suppress(Exception):
                self._expand_container.update()

    def _build_stats(self) -> None:
        """Build per-tool-type statistics rows (lazy, first expand only)."""
        if not self._stats_column:
            return

        counter = Counter(tool.name for tool in self._tools)
        error_counter = Counter(
            tool.name for tool in self._tools if tool.is_error
        )

        rows: list[ft.Control] = []
        for name, count in counter.most_common():
            icon = _TOOL_ICONS.get(name, ft.Icons.BUILD_CIRCLE_OUTLINED)
            err = error_counter.get(name, 0)
            label = f"{name} x{count}"
            if err:
                label += f" ({err} failed)"

            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(icon, size=13, color=ft.Colors.PRIMARY, opacity=0.5),
                            ft.Text(label, size=11, weight=ft.FontWeight.W_500),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    border_radius=6,
                    bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
                )
            )

        # Add "show detail" button
        show_detail_btn = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.UNFOLD_MORE, size=13, opacity=0.5),
                    ft.Text(
                        t("chat.tool_group_expand"),
                        size=11,
                        opacity=0.5,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            on_click=self._load_detail,
            ink=True,
            border_radius=6,
        )
        rows.append(show_detail_btn)

        self._stats_column.controls = rows
        self._stats_column.visible = True

    def _load_detail(self, e: ft.ControlEvent) -> None:
        """Lazy-load full ToolCallBlock instances for each tool call."""
        if self._detail_loaded or not self._detail_column:
            return
        self._detail_loaded = True

        for tool in self._tools:
            self._detail_column.controls.append(
                ToolCallBlock(
                    tool_name=tool.name,
                    tool_input=tool.tool_input,
                    tool_output=tool.result,
                    is_error=tool.is_error,
                )
            )
        self._detail_column.visible = True
        with contextlib.suppress(Exception):
            self._detail_column.update()
