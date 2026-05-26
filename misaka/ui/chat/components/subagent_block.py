"""SubAgent block component.

Renders a distinct card for Task tool calls (sub-agent invocations),
clearly showing the subagent_type, description, and execution result.
"""

from __future__ import annotations

import contextlib

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import MONO_FONT_FAMILY

_SUBAGENT_TYPE_META: dict[str, tuple[str, str]] = {
    "generalPurpose": (ft.Icons.SMART_TOY_OUTLINED, "General Purpose"),
    "explore": (ft.Icons.EXPLORE_OUTLINED, "Explorer"),
    "shell": (ft.Icons.TERMINAL_ROUNDED, "Shell"),
    "code-reviewer": (ft.Icons.RATE_REVIEW_OUTLINED, "Code Reviewer"),
    "ci-investigator": (ft.Icons.BUG_REPORT_OUTLINED, "CI Investigator"),
    "best-of-n-runner": (ft.Icons.FORK_RIGHT_ROUNDED, "Best-of-N Runner"),
    "cursor-guide": (ft.Icons.HELP_OUTLINE_ROUNDED, "Cursor Guide"),
}

_DEFAULT_ICON = ft.Icons.SMART_TOY_OUTLINED
_DEFAULT_LABEL = "SubAgent"


class SubAgentBlock(ft.Container):
    """Distinct display card for Task (sub-agent) tool invocations.

    Differentiates sub-agent calls from regular tool calls by
    showing: subagent_type badge, description, prompt preview,
    and execution result in a visually distinct card.
    """

    def __init__(
        self,
        tool_input: dict | None = None,
        tool_output: str | None = None,
        is_error: bool = False,
        initially_expanded: bool = False,
    ) -> None:
        super().__init__()
        self._tool_input = tool_input or {}
        self._tool_output = tool_output
        self._is_error = is_error
        self._expanded = initially_expanded
        self._detail_container: ft.Container | None = None
        self._chevron: ft.Icon | None = None
        self._build_ui()

    def _extract_metadata(self) -> tuple[str, str, str, str]:
        """Extract subagent_type, description, prompt, and model from input."""
        subagent_type = self._tool_input.get("subagent_type", "")
        description = self._tool_input.get("description", "")
        prompt = self._tool_input.get("prompt", "")
        model = self._tool_input.get("model", "")
        return subagent_type, description, prompt, model

    def _get_type_meta(self, subagent_type: str) -> tuple[str, str]:
        """Get icon and label for a given subagent_type."""
        if subagent_type in _SUBAGENT_TYPE_META:
            return _SUBAGENT_TYPE_META[subagent_type]
        return _DEFAULT_ICON, subagent_type or _DEFAULT_LABEL

    def _build_ui(self) -> None:
        subagent_type, description, prompt, model = self._extract_metadata()
        icon_name, type_label = self._get_type_meta(subagent_type)

        status_color = (
            ft.Colors.ERROR if self._is_error
            else ft.Colors.GREEN if self._tool_output is not None
            else ft.Colors.AMBER
        )

        self._chevron = ft.Icon(
            ft.Icons.EXPAND_MORE_ROUNDED if self._expanded
            else ft.Icons.CHEVRON_RIGHT_ROUNDED,
            size=14,
            opacity=0.4,
        )

        type_badge = ft.Container(
            content=ft.Text(
                type_label,
                size=10,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_PRIMARY_CONTAINER,
            ),
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

        header_controls = [
            ft.Container(
                width=6, height=6,
                border_radius=3,
                bgcolor=status_color,
            ),
            ft.Icon(icon_name, size=16, color=ft.Colors.PRIMARY),
            ft.Text(
                t("chat.subagent_label"),
                size=12,
                weight=ft.FontWeight.W_600,
            ),
            type_badge,
        ]

        if description:
            header_controls.append(
                ft.Text(
                    description,
                    size=11,
                    opacity=0.5,
                    expand=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
        else:
            header_controls.append(ft.Container(expand=True))

        if model:
            header_controls.append(
                ft.Text(model, size=10, opacity=0.35, italic=True)
            )

        header_controls.append(self._chevron)

        summary_row = ft.Row(
            controls=header_controls,
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        detail_controls = self._build_detail_controls(prompt)
        self._detail_container = ft.Container(
            content=ft.Column(controls=detail_controls, spacing=6, tight=True),
            visible=self._expanded,
            padding=ft.Padding.only(left=28, right=8, top=6, bottom=8),
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
                self._detail_container,
            ],
            spacing=0,
            tight=True,
        )
        self.border_radius = 10
        self.margin = ft.Margin.only(top=2, bottom=2)
        self.bgcolor = ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY)
        self.border = ft.Border.all(
            1, ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
        )

    def _build_detail_controls(self, prompt: str) -> list[ft.Control]:
        """Build detail section: prompt preview + output."""
        controls: list[ft.Control] = []

        if prompt:
            display_prompt = prompt[:500] + ("..." if len(prompt) > 500 else "")
            controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                t("chat.subagent_prompt"),
                                size=9,
                                weight=ft.FontWeight.W_600,
                                opacity=0.4,
                            ),
                            ft.Text(
                                display_prompt,
                                size=10,
                                selectable=True,
                                no_wrap=False,
                                max_lines=8,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=2,
                        tight=True,
                    ),
                    padding=8,
                    border_radius=6,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                )
            )

        if self._tool_output:
            output_color = ft.Colors.ERROR if self._is_error else None
            display = self._tool_output
            if len(display) > 1000:
                display = display[:1000] + "\n... (truncated)"
            controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                t("chat.subagent_error") if self._is_error else t("chat.subagent_result"),
                                size=9,
                                weight=ft.FontWeight.W_600,
                                opacity=0.4,
                                color=output_color,
                            ),
                            ft.Text(
                                display,
                                font_family=MONO_FONT_FAMILY,
                                size=10,
                                selectable=True,
                                no_wrap=False,
                                color=output_color,
                                max_lines=10,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=2,
                        tight=True,
                    ),
                    padding=8,
                    border_radius=6,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                )
            )

        if not controls:
            controls.append(
                ft.Text(
                    t("chat.subagent_running") if self._tool_output is None else t("chat.subagent_no_details"),
                    size=10, italic=True, opacity=0.3,
                )
            )

        return controls

    def _toggle(self, e: ft.ControlEvent) -> None:
        """Toggle expanded state."""
        self._expanded = not self._expanded
        if self._detail_container:
            self._detail_container.visible = self._expanded
            with contextlib.suppress(Exception):
                self._detail_container.update()
        if self._chevron:
            self._chevron.name = (
                ft.Icons.EXPAND_MORE_ROUNDED if self._expanded
                else ft.Icons.CHEVRON_RIGHT_ROUNDED
            )
            with contextlib.suppress(Exception):
                self._chevron.update()
