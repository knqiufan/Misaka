"""Tests for ToolCallBlock lazy detail rendering."""

from __future__ import annotations

from misaka.ui.chat.components.tool_call_block import ToolCallBlock


class TestToolCallBlockLazy:
    def test_collapsed_does_not_build_details(self) -> None:
        block = ToolCallBlock(
            tool_name="Read",
            tool_input={"file_path": "/tmp/example.py"},
            tool_output="file contents " * 200,
            initially_expanded=False,
        )
        assert block._detail_built is False
        assert block._detail_container is not None
        assert block._detail_container.content is None

    def test_ensure_detail_built_on_expand(self) -> None:
        block = ToolCallBlock(
            tool_name="Bash",
            tool_input={"command": "ls -la"},
            tool_output="ok",
            initially_expanded=False,
        )
        block._ensure_detail_built()
        assert block._detail_built is True
        assert block._detail_container is not None
        assert block._detail_container.content is not None

    def test_initially_expanded_builds_details(self) -> None:
        block = ToolCallBlock(
            tool_name="Grep",
            tool_input={"pattern": "foo"},
            initially_expanded=True,
        )
        assert block._detail_built is True
        assert block._detail_container is not None
        assert block._detail_container.content is not None

    def test_update_output_without_built_detail_keeps_lazy(self) -> None:
        block = ToolCallBlock(
            tool_name="Read",
            tool_input={"file_path": "/a"},
            initially_expanded=False,
        )
        block.update_output("done", is_error=False)
        assert block._detail_built is False
        assert block._detail_container is not None
        assert block._detail_container.content is None
