"""Streaming message component.

Renders the in-progress assistant response as it streams in,
with live-updating text, tool call blocks, and a progress indicator.
"""

from __future__ import annotations

import contextlib
import webbrowser
from typing import TYPE_CHECKING

import flet as ft

from misaka.config import get_assets_path
from misaka.i18n import t
from misaka.state import StreamingTextBlock, StreamingThinkingBlock, StreamingToolUseBlock
from misaka.ui.chat.components.tool_rendering import (
    render_streaming_tool_segment,
    segment_streaming_blocks,
)

if TYPE_CHECKING:
    from misaka.state import AppState, StreamingThinkingBlock, StreamingToolUseBlock


class StreamingMessage(ft.Container):
    """Live-updating display of a streaming assistant response."""

    def __init__(
        self,
        state: AppState,
        *,
        assistant_label: str = "Claude",
    ) -> None:
        super().__init__()
        self.state = state
        self._assistant_label = assistant_label
        self._pulse_low = True
        # Incremental update tracking
        self._content_column: ft.Column | None = None
        self._rendered_block_count: int = 0
        self._last_text_widget: ft.Text | ft.Markdown | None = None
        self._last_text_content: str | None = None
        self._last_text_wrapper: ft.Container | None = None
        # Incremental blockquote flag (avoids regex every frame)
        self._has_blockquote: bool = False
        # Whether the current wrapper container has blockquote styling applied
        self._wrapper_has_blockquote: bool = False
        # Whether last text block is using lightweight ft.Text (streaming) vs ft.Markdown
        self._streaming_text_mode: bool = False
        self._build_ui()

    def did_mount(self) -> None:
        """Start the thinking pulse animation after mounting."""
        self._start_thinking_pulse()

    def _is_attached_to_page(self) -> bool:
        """Return whether this control is attached to a page."""
        with contextlib.suppress(RuntimeError):
            return self.page is not None
        return False

    def _start_thinking_pulse(self) -> None:
        """Toggle the thinking indicator opacity to create a pulse effect."""
        if self._thinking_container and self._is_attached_to_page():
            self._thinking_container.opacity = 0.5 if self._pulse_low else 0.9
            self._pulse_low = not self._pulse_low
            with contextlib.suppress(Exception):
                self._thinking_container.update()

    # ------------------------------------------------------------------
    # Thinking block rendering
    # ------------------------------------------------------------------

    def _build_thinking_block(self, thinking_text: str) -> ft.Control:
        """Build a collapsible block displaying the model's reasoning process."""
        md = self._create_markdown(thinking_text)
        detail_container = ft.Container(
            content=md,
            padding=ft.Padding.only(left=12, top=8, right=8, bottom=8),
            visible=False,
        )
        chevron = ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=14, opacity=0.5)

        def toggle(_: ft.ControlEvent) -> None:
            detail_container.visible = not detail_container.visible
            chevron.name = (
                ft.Icons.EXPAND_MORE_ROUNDED if detail_container.visible
                else ft.Icons.CHEVRON_RIGHT_ROUNDED
            )
            with contextlib.suppress(Exception):
                detail_container.update()
                chevron.update()

        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PSYCHOLOGY_ROUNDED, size=14, color=ft.Colors.SECONDARY),
                    ft.Text(
                        t("chat.thinking"),
                        size=11,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.SECONDARY,
                    ),
                    chevron,
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=toggle,
            ink=True,
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
        )

        return ft.Container(
            content=ft.Column(controls=[header, detail_container], spacing=0, tight=True),
            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.SECONDARY),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.SECONDARY)),
            border_radius=8,
        )

    # ------------------------------------------------------------------
    # Markdown rendering helpers
    # ------------------------------------------------------------------

    def _create_markdown(self, value: str) -> ft.Markdown:
        """Create a Markdown component with consistent styling."""
        return ft.Markdown(
            value=value,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme=ft.MarkdownCodeTheme.GITHUB,
            on_tap_link=self._handle_link,
        )

    def _create_streaming_text(self, text: str) -> ft.Text:
        """Create a lightweight ft.Text widget for streaming display.

        Avoids the overhead of ft.Markdown's full AST re-parse on every
        frame.  Used during streaming; replaced by ft.Markdown in
        ``finalize_render()`` when streaming ends.
        """
        return ft.Text(
            value=text,
            selectable=True,
            style=ft.TextStyle(
                size=14,
            ),
        )

    def _handle_link(self, e: ft.MarkdownTapLinkEvent) -> None:
        """Open clicked link in the default browser."""
        if e.page and e.link:
            webbrowser.open(e.link)

    def _wrap_text_widget(self, widget: ft.Text | ft.Markdown, text: str) -> ft.Container:
        """Wrap a text widget in a container with optional blockquote styling."""
        self._wrapper_has_blockquote = self._has_blockquote
        if self._has_blockquote:
            return ft.Container(
                content=widget,
                border=ft.Border(
                    left=ft.BorderSide(3, ft.Colors.PRIMARY),
                ),
                padding=ft.Padding.only(left=12, top=4, bottom=4, right=8),
            )

        return ft.Container(
            content=widget,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
        )

    @staticmethod
    def _check_blockquote_incremental(text: str) -> bool:
        """Check whether text contains any blockquote lines."""
        return any(line.lstrip().startswith("> ") for line in text.split("\n"))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._thinking_container: ft.Container | None = None
        self._content_column = None
        self._rendered_block_count = 0
        self._last_text_widget = None
        self._last_text_content = None
        self._last_text_wrapper = None
        self._has_blockquote = False
        self._wrapper_has_blockquote = False
        self._streaming_text_mode = False
        if not self.state.is_streaming:
            self.visible = False
            self.content = ft.Container()
            return

        self.visible = True
        controls: list[ft.Control] = []

        # Role label with progress indicator
        claude_icon_path = str(get_assets_path() / "claude.png")
        controls.append(
            ft.Row(
                controls=[
                    ft.Image(
                        src=claude_icon_path,
                        width=14,
                        height=14,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    ft.Text(
                        self._assistant_label,
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.PRIMARY,
                    ),
                    ft.ProgressRing(width=12, height=12, stroke_width=1.5),
                ],
                spacing=6,
            )
        )

        segments = segment_streaming_blocks(self.state.streaming_blocks)
        for segment in segments:
            if not segment:
                continue
            first = segment[0]
            if isinstance(first, StreamingToolUseBlock) and first.name:
                controls.extend(render_streaming_tool_segment(segment))
                self._last_text_widget = None
                self._last_text_wrapper = None
                continue
            block = first
            if isinstance(block, StreamingThinkingBlock) and block.thinking:
                controls.append(self._build_thinking_block(block.thinking))
                self._last_text_widget = None
                self._last_text_wrapper = None
            elif isinstance(block, StreamingTextBlock) and block.text:
                text_widget = self._create_streaming_text(block.text)
                self._has_blockquote = self._check_blockquote_incremental(block.text)
                wrapped = self._wrap_text_widget(text_widget, block.text)
                controls.append(wrapped)
                self._last_text_widget = text_widget
                self._last_text_content = block.text
                self._last_text_wrapper = wrapped
                self._streaming_text_mode = True

        self._rendered_block_count = len(self.state.streaming_blocks)

        if len(controls) == 1:
            # Only header, no content yet - show enhanced thinking indicator
            self._thinking_container = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.ProgressRing(
                            width=14,
                            height=14,
                            stroke_width=1.5,
                            color=ft.Colors.PRIMARY,
                        ),
                        ft.Text(
                            "Thinking...",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.PRIMARY,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.PRIMARY),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                opacity=0.5 if self._pulse_low else 0.9,
                animate_opacity=ft.Animation(600, ft.AnimationCurve.EASE_IN_OUT),
            )
            controls.append(self._thinking_container)

        self._content_column = ft.Column(controls=controls, spacing=8)
        self.content = self._content_column
        self.padding = ft.Padding.symmetric(horizontal=20, vertical=12)
        self.margin = ft.Margin.only(bottom=4)
        self.border_radius = 10

    def _incremental_update(self) -> None:
        """Update the streaming display incrementally when possible.

        Most common case during streaming: last block is text and block
        count unchanged → update ft.Text value in-place (cheap).
        """
        if not self.state.is_streaming:
            self._build_ui()
            return

        # No content column yet → full build needed
        if self._content_column is None:
            self._build_ui()
            return

        blocks = self.state.streaming_blocks
        current_count = len(blocks)

        # Most common streaming case: same block count, last block is text
        if (
            current_count == self._rendered_block_count
            and current_count > 0
            and self._last_text_widget is not None
            and hasattr(blocks[-1], "text")
        ):
            new_text = blocks[-1].text
            old_text = self._last_text_content or ""

            # Incremental blockquote detection: only check the new delta
            if new_text.startswith(old_text):
                delta = new_text[len(old_text):]
                if delta:
                    self._has_blockquote = self._has_blockquote or any(
                        line.lstrip().startswith("> ") for line in delta.split("\n")
                    )
            else:
                # Text was replaced entirely (rare) — full scan
                self._has_blockquote = self._check_blockquote_incremental(new_text)

            # Blockquote appeared → need wrapper change → full rebuild
            if self._has_blockquote and not self._wrapper_has_blockquote:
                self._build_ui()
                return

            # Lightweight ft.Text update (no Markdown AST re-parse)
            self._last_text_widget.value = new_text
            self._last_text_content = new_text
            with contextlib.suppress(Exception):
                self._last_text_widget.update()
            return

        if (
            current_count == self._rendered_block_count
            and current_count > 0
            and isinstance(blocks[-1], StreamingToolUseBlock)
        ):
            self._build_ui()
            return

        # New blocks added → append only new block controls
        if current_count > self._rendered_block_count:
            # Remove thinking indicator if it was showing
            if self._thinking_container is not None:
                col_controls = self._content_column.controls
                if col_controls and len(col_controls) >= 2:
                    col_controls.pop()
                self._thinking_container = None

            for i in range(self._rendered_block_count, current_count):
                block = blocks[i]
                if hasattr(block, "thinking"):
                    thinking_block_inc: StreamingThinkingBlock = block  # type: ignore[assignment]
                    if thinking_block_inc.thinking:
                        self._content_column.controls.append(
                            self._build_thinking_block(thinking_block_inc.thinking)
                        )
                    self._last_text_widget = None
                    self._last_text_wrapper = None
                elif hasattr(block, "text"):
                    text_widget = self._create_streaming_text(block.text or "")
                    self._has_blockquote = self._check_blockquote_incremental(block.text or "")
                    wrapped = self._wrap_text_widget(text_widget, block.text or "")
                    self._content_column.controls.append(wrapped)
                    self._last_text_widget = text_widget
                    self._last_text_content = block.text or ""
                    self._last_text_wrapper = wrapped
                    self._streaming_text_mode = True
                elif isinstance(block, StreamingToolUseBlock):
                    self._build_ui()
                    return

            self._rendered_block_count = current_count
            return

        # Block count decreased or other structural change → full rebuild
        self._build_ui()

    def refresh(self) -> None:
        """Rebuild the streaming display from current state."""
        self._incremental_update()
        if self._thinking_container is not None:  # Only during thinking phase
            self._start_thinking_pulse()

    def finalize_render(self) -> None:
        """Replace lightweight ft.Text widgets with ft.Markdown for final display.

        Called once when streaming ends.  During streaming, ft.Text is used
        because it only needs a simple value update (~O(1)).  This method
        performs the single, more expensive Markdown render pass for proper
        formatted display (bold, links, lists, code blocks, etc.).
        """
        if (
            self._last_text_widget is None
            or self._last_text_wrapper is None
            or not self._streaming_text_mode
        ):
            return

        final_text = self._last_text_content or ""
        md = self._create_markdown(final_text)

        # Replace the ft.Text inside the wrapper with ft.Markdown
        self._last_text_wrapper.content = md
        self._last_text_widget = md
        self._streaming_text_mode = False

        with contextlib.suppress(Exception):
            self._last_text_wrapper.update()
