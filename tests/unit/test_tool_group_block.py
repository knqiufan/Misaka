"""Unit tests for ToolGroupBlock component logic."""

from __future__ import annotations

import pytest

from misaka.ui.chat.components.tool_group_block import ToolCallInfo, ToolGroupBlock


class TestToolCallInfo:
    """Tests for ToolCallInfo data class."""

    def test_basic_creation(self):
        info = ToolCallInfo(name="Read", tool_input={"path": "/test"})
        assert info.name == "Read"
        assert info.tool_input == {"path": "/test"}
        assert info.result is None
        assert info.is_error is False

    def test_with_result(self):
        info = ToolCallInfo(name="Bash", result="output", is_error=False)
        assert info.result == "output"

    def test_with_error(self):
        info = ToolCallInfo(name="Write", result="permission denied", is_error=True)
        assert info.is_error is True


class TestToolGroupBlock:
    """Tests for ToolGroupBlock rendering and state."""

    def _make_tools(self, count: int, name: str = "Read") -> list[ToolCallInfo]:
        return [ToolCallInfo(name=name, tool_input={"path": f"/file{i}"}) for i in range(count)]

    def test_summary_single_tool_type(self):
        tools = self._make_tools(5)
        block = ToolGroupBlock(tools)
        assert "Read x5" in block._summary_text

    def test_summary_multiple_tool_types(self):
        tools = [
            ToolCallInfo(name="Read"),
            ToolCallInfo(name="Read"),
            ToolCallInfo(name="Read"),
            ToolCallInfo(name="Write"),
            ToolCallInfo(name="Bash"),
        ]
        block = ToolGroupBlock(tools)
        assert "Read x3" in block._summary_text
        assert "Write x1" in block._summary_text
        assert "Bash x1" in block._summary_text

    def test_initially_collapsed(self):
        tools = self._make_tools(4)
        block = ToolGroupBlock(tools)
        assert block._expanded is False

    def test_detail_not_loaded_initially(self):
        tools = self._make_tools(4)
        block = ToolGroupBlock(tools)
        assert block._detail_loaded is False

    def test_error_count(self):
        tools = [
            ToolCallInfo(name="Read", is_error=False),
            ToolCallInfo(name="Write", is_error=True),
            ToolCallInfo(name="Bash", is_error=True),
        ]
        block = ToolGroupBlock(tools)
        assert block._count_errors() == 2

    def test_empty_tools_list(self):
        block = ToolGroupBlock([])
        assert block._summary_text == ""

    def test_compute_summary_preserves_order(self):
        tools = [
            ToolCallInfo(name="Bash"),
            ToolCallInfo(name="Bash"),
            ToolCallInfo(name="Bash"),
            ToolCallInfo(name="Read"),
        ]
        block = ToolGroupBlock(tools)
        # Most common first
        assert block._summary_text.startswith("Bash x3")
