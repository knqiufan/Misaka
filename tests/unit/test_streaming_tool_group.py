"""Tests for streaming tool grouping (P3)."""

from __future__ import annotations

from misaka.state import StreamingToolUseBlock
from misaka.ui.chat.components.tool_group_block import ToolGroupBlock
from misaka.ui.chat.components.tool_rendering import (
    flush_streaming_tool_run,
    segment_streaming_blocks,
)


class TestStreamingToolGroup:
    def test_segment_consecutive_tools(self) -> None:
        blocks = [
            StreamingToolUseBlock(id="1", name="Glob", input={"pattern": "**/*"}),
            StreamingToolUseBlock(id="2", name="Glob", input={"pattern": "*.py"}),
            StreamingToolUseBlock(id="3", name="Read", input={"path": "/a"}),
        ]
        segments = segment_streaming_blocks(blocks)
        assert len(segments) == 1
        assert len(segments[0]) == 3

    def test_flush_three_tools_yields_group(self) -> None:
        blocks = [
            StreamingToolUseBlock(id=str(i), name="Glob", input={})
            for i in range(3)
        ]
        rendered = flush_streaming_tool_run(blocks)
        assert len(rendered) == 1
        assert isinstance(rendered[0], ToolGroupBlock)
