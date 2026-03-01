"""Tool call block component.

Renders a tool invocation as a compact summary row that expands
to show input/output details on click.
"""

from __future__ import annotations

import json

import flet as ft

from misaka.ui.theme import (
    ERROR_RED,
    MONO_FONT_FAMILY,
    SUCCESS_GREEN,
    WARNING_AMBER,
)

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

_STATUS_COLORS = {
    "success": SUCCESS_GREEN,
    "error": ERROR_RED,
    "pending": WARNING_AMBER,
}


class ToolCallBlock(ft.Container):
    """Compact tool call display: summary row + expandable details."""

    def __init__(
        self,
        tool_name: str,
        tool_input: dict | None = None,
        tool_output: str | None = None,
        is_error: bool = False,
        initially_expanded: bool = False,
    ) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._tool_input = tool_input
        self._tool_output = tool_output
        self._is_error = is_error
        self._expanded = initially_expanded
        self._detail_container: ft.Container | None = None
        self._chevron: ft.Icon | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        icon = _TOOL_ICONS.get(self._tool_name, ft.Icons.BUILD_CIRCLE_OUTLINED)
        summary = self._get_input_summary()

        status_color = (
            _STATUS_COLORS["error"] if self._is_error
            else _STATUS_COLORS["success"] if self._tool_output is not None
            else _STATUS_COLORS["pending"]
        )

        self._chevron = ft.Icon(
            ft.Icons.EXPAND_MORE_ROUNDED if self._expanded else ft.Icons.CHEVRON_RIGHT_ROUNDED,
            size=14,
            opacity=0.3,
        )

        summary_row = ft.Row(
            controls=[
                ft.Container(width=5, height=5, border_radius=3, bgcolor=status_color),
                ft.Icon(icon, size=14, color=ft.Colors.PRIMARY, opacity=0.6),
                ft.Text(
                    self._tool_name,
                    size=11,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    summary,
                    size=11,
                    opacity=0.35,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                ),
                self._chevron,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        detail_controls = self._build_detail_controls()
        self._detail_container = ft.Container(
            content=ft.Column(controls=detail_controls, spacing=4, tight=True),
            visible=self._expanded,
            padding=ft.Padding.only(left=26, right=8, top=4, bottom=6),
        )

        self.content = ft.Column(
            controls=[
                ft.Container(
                    content=summary_row,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                    on_click=self._toggle,
                    ink=True,
                    border_radius=8,
                ),
                self._detail_container,
            ],
            spacing=0,
            tight=True,
        )
        self.border_radius = 10
        self.margin = ft.Margin.only(top=2, bottom=2)
        self.bgcolor = ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
        self.border = ft.Border.all(
            1, ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        )
        self.shadow = ft.BoxShadow(
            blur_radius=4,
            spread_radius=-2,
            color=ft.Colors.with_opacity(0.02, ft.Colors.BLACK),
            offset=ft.Offset(0, 1),
        )

    def _build_detail_controls(self) -> list[ft.Control]:
        controls: list[ft.Control] = []

        if self._tool_input:
            input_text = json.dumps(self._tool_input, indent=2, ensure_ascii=False)
            if len(input_text) > 1500:
                input_text = input_text[:1500] + "\n... (truncated)"
            controls.append(
                ft.Container(
                    content=ft.Column(controls=[
                        ft.Text(
                            "Input",
                            size=9,
                            weight=ft.FontWeight.W_600,
                            opacity=0.3,
                        ),
                        ft.Text(
                            input_text,
                            font_family=MONO_FONT_FAMILY,
                            size=10,
                            selectable=True,
                            no_wrap=False,
                        ),
                    ], spacing=2, tight=True),
                    padding=8,
                    border_radius=6,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                )
            )

        if self._tool_output:
            output_color = ft.Colors.ERROR if self._is_error else None
            display = self._tool_output
            if len(display) > 1500:
                display = display[:1500] + "\n... (truncated)"
            controls.append(
                ft.Container(
                    content=ft.Column(controls=[
                        ft.Text(
                            "Error" if self._is_error else "Output",
                            size=9,
                            weight=ft.FontWeight.W_600,
                            opacity=0.3,
                            color=output_color,
                        ),
                        ft.Text(
                            display,
                            font_family=MONO_FONT_FAMILY,
                            size=10,
                            selectable=True,
                            no_wrap=False,
                            color=output_color,
                        ),
                    ], spacing=2, tight=True),
                    padding=8,
                    border_radius=6,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                )
            )

        if not controls:
            controls.append(
                ft.Text("No details", size=10, italic=True, opacity=0.3)
            )

        return controls

    def _toggle(self, e: ft.ControlEvent) -> None:
        self._expanded = not self._expanded
        if self._detail_container:
            self._detail_container.visible = self._expanded
            self._detail_container.update()
        if self._chevron:
            self._chevron.name = (
                ft.Icons.EXPAND_MORE_ROUNDED if self._expanded
                else ft.Icons.CHEVRON_RIGHT_ROUNDED
            )
            self._chevron.update()

    def _get_input_summary(self) -> str:
        if not self._tool_input:
            return ""
        if self._tool_name in ("Read", "Write", "Edit"):
            path = self._tool_input.get("file_path", self._tool_input.get("path", ""))
            if path:
                parts = str(path).replace("\\", "/").split("/")
                return parts[-1] if parts else str(path)
        elif self._tool_name == "Bash":
            cmd = self._tool_input.get("command", "")
            if cmd:
                return cmd[:60] + ("..." if len(cmd) > 60 else "")
        elif self._tool_name in ("Glob", "Grep"):
            pattern = self._tool_input.get("pattern", "")
            if pattern:
                return pattern
        elif self._tool_name in ("WebFetch", "WebSearch"):
            val = self._tool_input.get("url", self._tool_input.get("query", ""))
            if val:
                return val[:50] + ("..." if len(val) > 50 else "")
        for key, val in self._tool_input.items():
            if isinstance(val, str) and val:
                short = val[:40] + ("..." if len(val) > 40 else "")
                return f"{key}: {short}"
        return ""

    def update_output(self, output: str, is_error: bool = False) -> None:
        self._tool_output = output
        self._is_error = is_error
        self._build_ui()
