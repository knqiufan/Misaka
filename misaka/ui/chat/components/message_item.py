"""Message item component.

Renders a single message with its content blocks (text, tool calls,
code blocks). Handles both user and assistant message styling with
markdown support and distinct visual treatment.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import flet as ft

from misaka.config import get_assets_path
from misaka.db.models import Message, MessageContentBlock
from misaka.ui.chat.components.code_block import CodeBlock
from misaka.ui.chat.components.tool_call_block import ToolCallBlock
from misaka.ui.common.theme import MONO_FONT_FAMILY


@dataclass
class _PairedTool:
    """A tool_use block paired with its corresponding tool_result."""
    name: str
    tool_input: dict
    result: str | None = None
    is_error: bool = False


class MessageItem(ft.Container):
    """Renders a single chat message with all its content blocks."""

    def __init__(
        self,
        message: Message,
        *,
        assistant_label: str = "Claude",
    ) -> None:
        super().__init__()
        self._message = message
        self._assistant_label = assistant_label
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

        header = self._build_header(is_user)

        self.content = ft.Column(
            controls=[header, *content_controls],
            spacing=8,
        )
        self.padding = ft.Padding.symmetric(horizontal=20, vertical=12)
        self.margin = ft.Margin.only(bottom=2)
        self.border_radius = 12
        if is_user:
            self.bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE)
            self.border = ft.Border.all(
                1, ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            )

    def _build_header(self, is_user: bool) -> ft.Control:
        if is_user:
            role_icon = ft.Icon(
                ft.Icons.PERSON_OUTLINE,
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        else:
            claude_icon_path = str(get_assets_path() / "claude.png")
            role_icon = ft.Image(
                src=claude_icon_path,
                width=14,
                height=14,
                fit=ft.BoxFit.CONTAIN,
            )
        role_label = ft.Text(
            "You" if is_user else self._assistant_label,
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.PRIMARY if not is_user else ft.Colors.ON_SURFACE_VARIANT,
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

        for block in blocks:
            if block.type == "text":
                text = block.text or ""
                if not text.strip():
                    continue
                ctrl = self._smart_render_text(text)
                if ctrl:
                    controls.append(ctrl)
                continue

            if block.type == "tool_use" and block.name:
                result_block = result_map.get(block.id or "") if block.id else None
                if block.id and result_block:
                    consumed_results.add(block.id)
                controls.append(
                    ToolCallBlock(
                        tool_name=block.name,
                        tool_input=block.input if isinstance(block.input, dict) else None,
                        tool_output=result_block.content if result_block else None,
                        is_error=result_block.is_error if result_block else False,
                    )
                )
                continue

            if block.type == "tool_result":
                if block.tool_use_id and block.tool_use_id in consumed_results:
                    continue
                controls.append(
                    ToolCallBlock(
                        tool_name="tool_result",
                        tool_input=None,
                        tool_output=block.content,
                        is_error=block.is_error,
                    )
                )
                continue

            if block.type == "code" and block.code:
                controls.append(
                    CodeBlock(code=block.code, language=block.language or "plaintext")
                )

        return controls

    def _smart_render_text(self, text: str) -> ft.Control | None:
        """Render text: detect raw JSON and show a collapsible summary instead."""
        stripped = text.strip()
        if self._looks_like_raw_json(stripped):
            return self._render_json_summary(stripped)
        return self._render_text_block(text)

    @staticmethod
    def _looks_like_raw_json(text: str) -> bool:
        if not text:
            return False
        if (text.startswith("{") and text.endswith("}")) or \
           (text.startswith("[") and text.endswith("]")):
            try:
                json.loads(text)
                return len(text) > 120
            except (json.JSONDecodeError, ValueError):
                pass
        return False

    def _render_json_summary(self, raw_json: str) -> ft.Control:
        """Build a compact summary for raw JSON with expandable detail."""
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, ValueError):
            return self._render_text_block(raw_json)

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
                    t = item.get("type", "")
                    if t:
                        types.add(t)
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
    # Block categorisation & pairing (assistant messages)
    # ------------------------------------------------------------------

    @staticmethod
    def _categorise_blocks(
        blocks: list[MessageContentBlock],
    ) -> tuple[list[_PairedTool], list[MessageContentBlock], list[MessageContentBlock]]:
        """Split blocks into paired tools, text blocks, and code blocks."""
        result_map: dict[str, MessageContentBlock] = {}
        for b in blocks:
            if b.type == "tool_result" and b.tool_use_id:
                result_map[b.tool_use_id] = b

        paired: list[_PairedTool] = []
        matched_result_ids: set[str] = set()

        for b in blocks:
            if b.type == "tool_use" and b.name:
                result_block = result_map.get(b.id or "") if b.id else None
                paired.append(_PairedTool(
                    name=b.name,
                    tool_input=b.input if isinstance(b.input, dict) else {},
                    result=result_block.content if result_block else None,
                    is_error=result_block.is_error if result_block else False,
                ))
                if b.id and result_block:
                    matched_result_ids.add(b.id)

        for b in blocks:
            if b.type == "tool_result" and b.tool_use_id not in matched_result_ids:
                paired.append(_PairedTool(
                    name="tool_result",
                    tool_input={},
                    result=b.content,
                    is_error=b.is_error,
                ))

        text_blocks = [b for b in blocks if b.type == "text" and b.text]
        code_blocks = [b for b in blocks if b.type == "code" and b.code]

        return paired, text_blocks, code_blocks

    @staticmethod
    def _render_tool_group(paired: list[_PairedTool]) -> ft.Control:
        tool_controls = [
            ToolCallBlock(
                tool_name=t.name,
                tool_input=t.tool_input if t.tool_input else None,
                tool_output=t.result,
                is_error=t.is_error,
            )
            for t in paired
        ]
        return ft.Column(controls=tool_controls, spacing=2)

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
        return None

    def _render_text_block(self, text: str) -> ft.Control:
        """Render a text block with markdown support."""
        segments = self._split_code_blocks(text)

        if len(segments) == 1 and segments[0][0] == "text":
            return ft.Markdown(
                value=segments[0][1],
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme=ft.MarkdownCodeTheme.GITHUB,
                auto_follow_links=True,
            )

        controls: list[ft.Control] = []
        for seg_type, seg_content in segments:
            if seg_type == "text" and seg_content.strip():
                controls.append(
                    ft.Markdown(
                        value=seg_content,
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme=ft.MarkdownCodeTheme.GITHUB,
                        auto_follow_links=True,
                    )
                )
            elif seg_type == "code":
                lang, code = seg_content
                controls.append(CodeBlock(code=code, language=lang))

        return ft.Column(controls=controls, spacing=4)

    @staticmethod
    def _split_code_blocks(text: str) -> list[tuple[str, ...]]:
        pattern = r"```(\w*)\n(.*?)```"
        segments: list[tuple[str, ...]] = []
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
