"""Streaming message component.

Renders the in-progress assistant response as it streams in,
with live-updating text, tool call blocks, and a progress indicator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.ui.components.code_block import CodeBlock
from misaka.ui.components.tool_call_block import ToolCallBlock

if TYPE_CHECKING:
    from misaka.state import AppState, StreamingTextBlock, StreamingToolUseBlock


class StreamingMessage(ft.Container):
    """Live-updating display of a streaming assistant response."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._build_ui()

    def _build_ui(self) -> None:
        if not self.state.is_streaming:
            self.visible = False
            self.content = ft.Container()
            return

        self.visible = True
        controls: list[ft.Control] = []

        # Role label
        controls.append(
            ft.Row(
                controls=[
                    ft.Text(
                        "Claude",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.PRIMARY,
                    ),
                    ft.ProgressRing(width=14, height=14, stroke_width=2),
                ],
                spacing=8,
            )
        )

        for block in self.state.streaming_blocks:
            if hasattr(block, "text") and block.text:
                # Streaming text - render as markdown
                controls.append(
                    ft.Markdown(
                        value=block.text,
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    )
                )
            elif hasattr(block, "name") and block.name:
                # Tool use block
                tool_block: StreamingToolUseBlock = block  # type: ignore[assignment]
                controls.append(
                    ToolCallBlock(
                        tool_name=tool_block.name,
                        tool_input=tool_block.input,
                        tool_output=tool_block.output,
                        is_error=tool_block.is_error,
                        initially_expanded=tool_block.output is None,
                    )
                )

        if len(controls) == 1:
            # Only header, no content yet - show thinking indicator
            controls.append(
                ft.Row(
                    controls=[
                        ft.Text("Thinking...", size=13, italic=True, opacity=0.6),
                    ],
                    spacing=8,
                )
            )

        self.content = ft.Column(controls=controls, spacing=6)
        self.padding = ft.Padding.symmetric(horizontal=16, vertical=10)
        self.margin = ft.Margin.only(bottom=4)
        self.border_radius = 8

    def refresh(self) -> None:
        """Rebuild the streaming display from current state."""
        self._build_ui()
