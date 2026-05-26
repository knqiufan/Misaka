"""Tests for assistant block segmentation (P0)."""

from __future__ import annotations

from misaka.db.models import MessageContentBlock
from misaka.ui.chat.components.tool_rendering import (
    build_result_map,
    flush_tool_run,
    segment_assistant_blocks,
)
from misaka.ui.chat.components.tool_group_block import ToolGroupBlock


def _pair(name: str, idx: int) -> list[MessageContentBlock]:
    tid = f"id-{idx}"
    return [
        MessageContentBlock(type="tool_use", id=tid, name=name, input={"pattern": "*"}),
        MessageContentBlock(
            type="tool_result", tool_use_id=tid, content="ok", is_error=False,
        ),
    ]


class TestSegmentAssistantBlocks:
    def test_interleaved_results_form_one_tool_run(self) -> None:
        blocks: list[MessageContentBlock] = []
        for i in range(5):
            blocks.extend(_pair("Glob", i))

        segments = segment_assistant_blocks(blocks)
        tool_segments = [s for s in segments if s[0].type == "tool_use"]
        assert len(tool_segments) == 1
        assert len(tool_segments[0]) == 5

    def test_thinking_breaks_tool_run(self) -> None:
        blocks = _pair("Read", 0) + _pair("Read", 1)
        blocks.insert(
            2,
            MessageContentBlock(type="thinking", thinking="plan"),
        )
        segments = segment_assistant_blocks(blocks)
        tool_segments = [s for s in segments if s[0].type == "tool_use"]
        assert len(tool_segments) == 2

    def test_flush_groups_five_glob_calls(self) -> None:
        blocks: list[MessageContentBlock] = []
        for i in range(5):
            blocks.extend(_pair("Glob", i))
        result_map = build_result_map(blocks)
        consumed: set[str] = set()
        segment = segment_assistant_blocks(blocks)[0]
        rendered = flush_tool_run(segment, result_map, consumed)
        assert len(rendered) == 1
        assert isinstance(rendered[0], ToolGroupBlock)
        assert len(rendered[0]._tools) == 5

    def test_orphan_tool_result_not_in_segments(self) -> None:
        blocks = [
            MessageContentBlock(
                type="tool_result",
                tool_use_id="missing",
                content="orphan",
            ),
        ]
        segments = segment_assistant_blocks(blocks)
        assert segments == []
