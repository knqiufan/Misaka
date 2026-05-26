"""Message item component.

Renders a single message with its content blocks (text, tool calls,
code blocks, images). Handles both user and assistant message styling
with markdown support and distinct visual treatment.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import webbrowser
from typing import cast

import flet as ft

from misaka.config import get_assets_path
from misaka.db.models import KBSearchResult, Message, MessageContentBlock
from misaka.i18n import t
from misaka.ui.chat.components.code_block import CodeBlock
from misaka.ui.chat.components.image_block import ImageBlock
from misaka.ui.chat.components.subagent_block import SubAgentBlock
from misaka.ui.chat.components.tool_call_block import ToolCallBlock
from misaka.ui.chat.components.tool_group_block import ToolCallInfo, ToolGroupBlock
from misaka.ui.common.theme import MONO_FONT_FAMILY, RADIUS_LG, make_icon_button


class MessageItem(ft.Container):
    """Renders a single chat message with all its content blocks."""

    def __init__(
        self,
        message: Message,
        *,
        assistant_label: str = "Claude",
        on_regenerate: object = None,
        rag_sources: list[KBSearchResult] | None = None,
    ) -> None:
        super().__init__()
        self._message = message
        self._assistant_label = assistant_label
        self._on_regenerate = on_regenerate
        self._rag_sources: list[KBSearchResult] = rag_sources or []
        self._build_ui()

    # ------------------------------------------------------------------
    # Main build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        is_user = self._message.role == "user"
        blocks = self._message.parse_content()

        content_controls: list[ft.Control] = []

        if is_user:
            for block in blocks:
                ctrl = self._render_block(block, is_user)
                if ctrl:
                    content_controls.append(ctrl)
        else:
            content_controls = self._render_assistant_blocks(blocks)

        # Hide message if all content is empty
        if not content_controls:
            self.visible = False
            self.content = ft.Container(height=0)
            return

        if is_user:
            bubble_copy_text = self._extract_markdown_from_blocks(blocks)
            self.content = self._build_user_layout(content_controls, bubble_copy_text)
        else:
            header = self._build_header()
            body = self._wrap_assistant_content(content_controls, blocks)
            col_controls = [header, body]
            if self._rag_sources:
                col_controls.append(self._build_rag_sources_panel())
            self.content = ft.Column(
                controls=col_controls,
                spacing=8,
            )

        self.padding = ft.Padding.symmetric(horizontal=20, vertical=12)
        self.margin = ft.Margin.only(bottom=2)
        self.border_radius = 12
        if is_user:
            self.bgcolor = None
            self.border = None

    def _build_user_layout(
        self,
        content_controls: list[ft.Control],
        bubble_copy_text: str,
    ) -> ft.Control:
        """Build right-aligned user message: content bubble + avatar on the right."""
        avatar = ft.Container(
            content=ft.Icon(
                ft.Icons.PERSON_OUTLINE,
                size=20,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            width=32,
            height=32,
            border_radius=16,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
            alignment=ft.Alignment.CENTER,
        )

        time_label = ft.Text(
            self._format_time(self._message.created_at),
            size=10,
            opacity=0.4,
        )

        bubble = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[time_label],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Column(controls=content_controls, spacing=8),
                ],
                spacing=6,
            ),
            expand=True,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.PRIMARY),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
            ),
            border_radius=ft.BorderRadius.only(
                top_left=RADIUS_LG,
                top_right=4,
                bottom_left=RADIUS_LG,
                bottom_right=RADIUS_LG,
            ),
        )

        copy_row = self._build_user_copy_row(bubble_copy_text)
        bubble_stack: list[ft.Control] = [bubble]
        if copy_row is not None:
            bubble_stack.append(copy_row)

        bubble_with_actions = ft.Column(
            controls=bubble_stack,
            spacing=4,
            expand=True,
        )

        # Spacer: 1 part, bubble column: 9 parts — bubble adapts to ~90% of available width
        return ft.Row(
            controls=[
                ft.Container(expand=1),
                ft.Container(content=bubble_with_actions, expand=9),
                ft.Container(content=avatar, margin=ft.Margin.only(left=10)),
            ],
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _build_user_copy_row(self, copy_text: str) -> ft.Row | None:
        """Copy control below the user bubble (outside border/bg); only when there is text."""
        if not copy_text.strip():
            return None
        copy_btn = make_icon_button(
            ft.Icons.CONTENT_COPY_ROUNDED,
            tooltip=t("chat.copy_user_message"),
            on_click=self._copy_to_clipboard,
            icon_size=14,
        )
        copy_btn.data = copy_text
        return ft.Row(
            controls=[ft.Container(expand=True), copy_btn],
            alignment=ft.MainAxisAlignment.END,
        )

    def _build_header(self) -> ft.Control:
        """Build header row for assistant messages (icon + label + time)."""
        claude_icon_path = str(get_assets_path() / "claude.png")
        role_icon = ft.Image(
            src=claude_icon_path,
            width=14,
            height=14,
            fit=ft.BoxFit.CONTAIN,
        )
        role_label = ft.Text(
            self._assistant_label,
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.PRIMARY,
        )
        time_label = ft.Text(
            self._format_time(self._message.created_at),
            size=10,
            opacity=0.3,
        )
        return ft.Row(
            controls=[role_icon, role_label, ft.Container(expand=True), time_label],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _wrap_assistant_content(
        self,
        controls: list[ft.Control],
        blocks: list[MessageContentBlock],
    ) -> ft.Column:
        """Build assistant output: content + copy icon row below (left-aligned)."""
        body_controls: list[ft.Control] = [
            ft.Column(controls=controls, spacing=8),
        ]

        action_btns: list[ft.Control] = []

        markdown_text = self._extract_markdown_from_blocks(blocks)
        if markdown_text:
            copy_btn = make_icon_button(
                ft.Icons.CONTENT_COPY_ROUNDED,
                tooltip=t("chat.copy_reply"),
                on_click=self._copy_to_clipboard,
                icon_size=14,
            )
            copy_btn.data = markdown_text
            action_btns.append(copy_btn)

        if self._on_regenerate:
            regen_btn = make_icon_button(
                ft.Icons.REFRESH_ROUNDED,
                tooltip=t("chat.regenerate"),
                on_click=self._handle_regenerate,
                icon_size=14,
            )
            action_btns.append(regen_btn)

        if action_btns:
            action_row = ft.Row(
                controls=action_btns,
                alignment=ft.MainAxisAlignment.START,
                spacing=4,
            )
            body_controls.append(action_row)

        return ft.Column(controls=body_controls, spacing=6)

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

    def _build_interrupted_banner(self) -> ft.Control:
        """Build error banner indicating the command was interrupted by user."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.CANCEL_OUTLINED,
                        color=ft.Colors.ERROR,
                        size=16,
                    ),
                    ft.Text(
                        t("chat.command_interrupted"),
                        size=12,
                        color=ft.Colors.ERROR,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ERROR),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.25, ft.Colors.ERROR),
            ),
            border_radius=8,
        )

    def _build_rag_sources_panel(self) -> ft.Control:
        """Build a collapsible panel showing RAG retrieval sources."""
        count = len(self._rag_sources)
        source_items = self._build_source_items()

        detail_container = ft.Container(
            content=ft.Column(controls=source_items, spacing=4, tight=True),
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
                    ft.Icon(
                        ft.Icons.MENU_BOOK_ROUNDED,
                        size=14,
                        color=ft.Colors.PRIMARY,
                    ),
                    ft.Text(
                        t("chat.rag_sources", count=count),
                        size=11,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.PRIMARY,
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
            content=ft.Column(
                controls=[header, detail_container],
                spacing=0,
                tight=True,
            ),
            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
            ),
            border_radius=8,
        )

    def _build_source_items(self) -> list[ft.Control]:
        """Build individual source citation rows."""
        items: list[ft.Control] = []
        for src in self._rag_sources:
            doc_name = src.document_name
            chunk_idx = src.chunk_index + 1
            score = src.score
            raw_content = src.content or ""
            content_preview = raw_content[:120]
            if len(raw_content) > 120:
                content_preview += "..."

            items.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.DESCRIPTION_OUTLINED,
                                        size=12,
                                        opacity=0.5,
                                    ),
                                    ft.Text(
                                        doc_name,
                                        size=11,
                                        weight=ft.FontWeight.W_500,
                                        expand=True,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        f"#{chunk_idx}",
                                        size=10,
                                        opacity=0.4,
                                    ),
                                    ft.Text(
                                        f"{score:.2f}",
                                        size=10,
                                        opacity=0.4,
                                        color=ft.Colors.PRIMARY,
                                    ),
                                ],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                content_preview,
                                size=10,
                                opacity=0.5,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=2,
                        tight=True,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    border_radius=6,
                    bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
                )
            )
        return items

    def _extract_markdown_from_blocks(
        self, blocks: list[MessageContentBlock]
    ) -> str:
        """Extract markdown representation from content blocks for copying."""
        parts: list[str] = []
        for block in blocks:
            if block.type == "interrupted":
                continue
            if block.type == "text" and block.text:
                parts.append(block.text.strip())
            elif block.type == "code" and block.code:
                lang = block.language or "plaintext"
                parts.append(f"```{lang}\n{block.code}\n```")
        return "\n\n".join(parts) if parts else ""

    async def _copy_to_clipboard(self, e: ft.ControlEvent) -> None:
        """Copy message markdown (assistant reply or user bubble) with visual feedback."""
        text = getattr(e.control, "data", None) if e.control else None
        if not text or not e.page:
            return
        await ft.Clipboard().set(text)
        if e.control and hasattr(e.control, "icon"):
            e.control.icon = ft.Icons.CHECK_ROUNDED
            e.control.icon_color = ft.Colors.GREEN
            e.control.update()
            await asyncio.sleep(1.5)
            e.control.icon = ft.Icons.CONTENT_COPY_ROUNDED
            e.control.icon_color = None
            with contextlib.suppress(Exception):
                e.control.update()

    def _handle_regenerate(self, e: ft.ControlEvent) -> None:
        """Trigger regeneration of this assistant response."""
        if self._on_regenerate:
            self._on_regenerate(self._message.id)

    # ------------------------------------------------------------------
    # Assistant message rendering
    # ------------------------------------------------------------------

    def _render_assistant_blocks(
        self, blocks: list[MessageContentBlock]
    ) -> list[ft.Control]:
        controls: list[ft.Control] = []
        result_map: dict[str, MessageContentBlock] = {
            b.tool_use_id: b
            for b in blocks
            if b.type == "tool_result" and b.tool_use_id
        }
        consumed_results: set[str] = set()

        # Collect blocks into segments: consecutive tool_use runs are grouped
        segments: list[list[MessageContentBlock]] = []
        current_tool_run: list[MessageContentBlock] = []

        for block in blocks:
            if block.type == "tool_use" and block.name:
                current_tool_run.append(block)
            else:
                if current_tool_run:
                    segments.append(current_tool_run)
                    current_tool_run = []
                segments.append([block])

        if current_tool_run:
            segments.append(current_tool_run)

        for segment in segments:
            if not segment:
                continue

            first = segment[0]

            # Segment of consecutive tool_use blocks
            if first.type == "tool_use" and first.name:
                rendered = self._render_tool_segment(
                    segment, result_map, consumed_results,
                )
                controls.extend(rendered)
                continue

            # Non-tool blocks (single block segments)
            block = first
            if block.type == "interrupted":
                controls.append(self._build_interrupted_banner())
            elif block.type == "thinking":
                thinking_text = block.thinking or ""
                if thinking_text.strip():
                    controls.append(self._build_thinking_block(thinking_text))
            elif block.type == "text":
                text = block.text or ""
                if text.strip():
                    ctrl = self._smart_render_text(text)
                    if ctrl:
                        controls.append(ctrl)
            elif block.type == "tool_result":
                if block.tool_use_id and block.tool_use_id in consumed_results:
                    pass
                else:
                    controls.append(
                        ToolCallBlock(
                            tool_name="tool_result",
                            tool_input=None,
                            tool_output=block.content,
                            is_error=block.is_error,
                        )
                    )
            elif block.type == "code" and block.code:
                controls.append(
                    CodeBlock(code=block.code, language=block.language or "plaintext")
                )
            elif block.type == "image":
                controls.append(
                    ImageBlock(block, on_click=self._handle_image_click)
                )

        return controls

    def _render_tool_segment(
        self,
        tool_blocks: list[MessageContentBlock],
        result_map: dict[str, MessageContentBlock],
        consumed_results: set[str],
    ) -> list[ft.Control]:
        """Render a consecutive sequence of tool_use blocks.

        - SubAgent (Task) calls get their own SubAgentBlock
        - Runs of 3+ non-SubAgent tools are collapsed into ToolGroupBlock
        - Shorter runs render individual ToolCallBlocks
        """
        controls: list[ft.Control] = []
        non_subagent_run: list[MessageContentBlock] = []

        for block in tool_blocks:
            is_subagent = block.name == "Task"

            if is_subagent:
                # Flush any accumulated non-subagent tools
                if non_subagent_run:
                    controls.extend(
                        self._flush_tool_run(non_subagent_run, result_map, consumed_results)
                    )
                    non_subagent_run = []

                # Render SubAgent block
                result_block = result_map.get(block.id or "") if block.id else None
                if block.id and result_block:
                    consumed_results.add(block.id)
                controls.append(
                    SubAgentBlock(
                        tool_input=block.input if isinstance(block.input, dict) else None,
                        tool_output=result_block.content if result_block else None,
                        is_error=result_block.is_error if result_block else False,
                    )
                )
            else:
                non_subagent_run.append(block)

        # Flush remaining non-subagent tools
        if non_subagent_run:
            controls.extend(
                self._flush_tool_run(non_subagent_run, result_map, consumed_results)
            )

        return controls

    def _flush_tool_run(
        self,
        tool_blocks: list[MessageContentBlock],
        result_map: dict[str, MessageContentBlock],
        consumed_results: set[str],
    ) -> list[ft.Control]:
        """Render a run of non-SubAgent tool calls.

        If 3+ consecutive, collapse into ToolGroupBlock; otherwise render individually.
        """
        if len(tool_blocks) >= 3:
            tool_infos: list[ToolCallInfo] = []
            for block in tool_blocks:
                result_block = result_map.get(block.id or "") if block.id else None
                if block.id and result_block:
                    consumed_results.add(block.id)
                tool_infos.append(ToolCallInfo(
                    name=block.name or "unknown",
                    tool_input=block.input if isinstance(block.input, dict) else None,
                    result=result_block.content if result_block else None,
                    is_error=result_block.is_error if result_block else False,
                ))
            return [ToolGroupBlock(tool_infos)]

        controls: list[ft.Control] = []
        for block in tool_blocks:
            result_block = result_map.get(block.id or "") if block.id else None
            if block.id and result_block:
                consumed_results.add(block.id)
            controls.append(
                ToolCallBlock(
                    tool_name=block.name or "unknown",
                    tool_input=block.input if isinstance(block.input, dict) else None,
                    tool_output=result_block.content if result_block else None,
                    is_error=result_block.is_error if result_block else False,
                )
            )
        return controls

    def _smart_render_text(self, text: str) -> ft.Control | None:
        """Render text: detect raw JSON and show a collapsible summary instead."""
        stripped = text.strip()
        parsed = self._try_parse_json(stripped)
        if parsed is not None:
            return self._render_json_summary(stripped, parsed)
        return self._render_text_block(text)

    @staticmethod
    def _try_parse_json(text: str):
        """Try to parse text as JSON; return parsed data if it looks like raw JSON, else None."""
        if not text:
            return None
        if (text.startswith("{") and text.endswith("}")) or \
           (text.startswith("[") and text.endswith("]")):
            try:
                data = json.loads(text)
                if len(text) > 120:
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _render_json_summary(self, raw_json: str, data: object) -> ft.Control:
        """Build a compact summary for raw JSON with expandable detail.

        ``data`` is the already-parsed JSON object, passed in from
        ``_smart_render_text`` to avoid a redundant ``json.loads`` call.
        """

        summary = self._extract_json_summary(data)

        detail_text = json.dumps(data, indent=2, ensure_ascii=False)
        if len(detail_text) > 3000:
            detail_text = detail_text[:3000] + "\n... (truncated)"

        detail_container = ft.Container(
            content=ft.Text(
                detail_text,
                font_family=MONO_FONT_FAMILY,
                size=10,
                selectable=True,
                no_wrap=False,
            ),
            padding=8,
            border_radius=6,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            visible=False,
        )

        chevron = ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=14, opacity=0.3)

        def toggle(e):
            detail_container.visible = not detail_container.visible
            chevron.name = (
                ft.Icons.EXPAND_MORE_ROUNDED if detail_container.visible
                else ft.Icons.CHEVRON_RIGHT_ROUNDED
            )
            with contextlib.suppress(Exception):
                detail_container.update()
                chevron.update()

        summary_row = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DATA_OBJECT, size=13, color=ft.Colors.PRIMARY, opacity=0.5),
                    ft.Text(summary, size=11, opacity=0.5, expand=True,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    chevron,
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=toggle,
            ink=True,
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE)),
        )

        return ft.Column(controls=[summary_row, detail_container], spacing=2, tight=True)

    @staticmethod
    def _extract_json_summary(data) -> str:
        """Extract a concise human-readable summary from parsed JSON."""
        if isinstance(data, dict):
            parts: list[str] = []
            if "type" in data:
                parts.append(f"type={data['type']}")
            if "name" in data:
                parts.append(f"name={data['name']}")
            if "caller" in data:
                parts.append("caller")
            if "plan" in data:
                plan = str(data["plan"])
                parts.append(f"plan: {plan[:60]}{'...' if len(plan) > 60 else ''}")
            if "allowedPrompts" in data:
                parts.append("allowedPrompts")
            if "tool" in data:
                parts.append(f"tool={data['tool']}")
            if "prompt" in data:
                p = str(data["prompt"])
                parts.append(f"prompt: {p[:50]}{'...' if len(p) > 50 else ''}")
            if parts:
                return " | ".join(parts)
            keys = list(data.keys())[:5]
            return "{ " + ", ".join(keys) + (" ..." if len(data) > 5 else "") + " }"

        if isinstance(data, list):
            if not data:
                return "[]"
            types = set()
            names = []
            for item in data[:10]:
                if isinstance(item, dict):
                    item_type = item.get("type", "")
                    if item_type:
                        types.add(item_type)
                    n = item.get("name", "")
                    if n:
                        names.append(n)
            parts = []
            if types:
                parts.append(f"types: {', '.join(sorted(types))}")
            if names:
                parts.append(f"names: {', '.join(names[:5])}")
            parts.append(f"{len(data)} items")
            return " | ".join(parts)

        return str(data)[:80]

    # ------------------------------------------------------------------
    # Single-block rendering (user messages / fallback)
    # ------------------------------------------------------------------

    def _render_block(
        self, block: MessageContentBlock, is_user: bool
    ) -> ft.Control | None:
        if block.type == "text" and block.text:
            return self._render_text_block(block.text)
        elif block.type == "code" and block.code:
            return CodeBlock(code=block.code, language=block.language or "plaintext")
        elif block.type == "image":
            return ImageBlock(block, on_click=self._handle_image_click)
        return None

    def _handle_image_click(self, image_src: str) -> None:
        """Handle click on an image to view full-size."""
        from misaka.ui.components.image_overlay import show_image_overlay
        if self.page:
            show_image_overlay(self.page, image_src)

    def _render_text_block(self, text: str) -> ft.Control:
        """Render a text block with markdown support and enhanced styling."""
        segments = self._split_code_blocks(text)

        if len(segments) == 1 and segments[0][0] == "text":
            return self._wrap_markdown(
                self._create_markdown(segments[0][1]),
                segments[0][1],
            )

        controls: list[ft.Control] = []
        for seg_type, seg_content in segments:
            if seg_type == "text" and seg_content.strip():
                controls.append(
                    self._wrap_markdown(
                        self._create_markdown(seg_content),
                        seg_content,
                    )
                )
            elif seg_type == "code":
                lang, code = cast(tuple[str, str], seg_content)
                controls.append(CodeBlock(code=code, language=lang))

        return ft.Column(controls=controls, spacing=10)

    def _create_markdown(self, value: str) -> ft.Markdown:
        """Create a Markdown component with consistent styling."""
        return ft.Markdown(
            value=value,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme=ft.MarkdownCodeTheme.GITHUB,
            on_tap_link=self._handle_link,
        )

    def _handle_link(self, e: ft.MarkdownTapLinkEvent) -> None:
        """Open clicked link in the default browser."""
        if e.page and e.link:
            webbrowser.open(e.link)

    def _wrap_markdown(self, md: ft.Markdown, text: str) -> ft.Control:
        """Wrap markdown in a container with optional blockquote styling."""
        # Check for blockquote (lines starting with >)
        has_blockquote = bool(re.search(r"^>\s", text, re.MULTILINE))

        if has_blockquote:
            return ft.Container(
                content=md,
                border=ft.Border(
                    left=ft.BorderSide(3, ft.Colors.PRIMARY),
                ),
                padding=ft.Padding.only(left=12, top=4, bottom=4, right=8),
            )

        return ft.Container(
            content=md,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
        )

    @staticmethod
    def _split_code_blocks(text: str) -> list[tuple[str, str] | tuple[str, tuple[str, str]]]:
        pattern = r"```(\w*)\n(.*?)```"
        segments: list[tuple[str, str] | tuple[str, tuple[str, str]]] = []
        last_end = 0

        for match in re.finditer(pattern, text, re.DOTALL):
            before = text[last_end:match.start()]
            if before.strip():
                segments.append(("text", before))
            lang = match.group(1) or "plaintext"
            code = match.group(2).rstrip("\n")
            segments.append(("code", (lang, code)))
            last_end = match.end()

        remaining = text[last_end:]
        if remaining.strip():
            segments.append(("text", remaining))

        if not segments:
            segments.append(("text", text))

        return segments

    @staticmethod
    def _format_time(iso_str: str) -> str:
        from misaka.utils.time_utils import format_short_time
        return format_short_time(iso_str)
