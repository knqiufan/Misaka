"""Tests for SubAgentBlock lazy detail rendering."""

from __future__ import annotations

from misaka.ui.chat.components.subagent_block import SubAgentBlock


class TestSubAgentBlockLazy:
    def test_collapsed_does_not_build_details(self) -> None:
        block = SubAgentBlock(
            tool_input={
                "subagent_type": "explore",
                "description": "Find handlers",
                "prompt": "x" * 600,
            },
            tool_output="result " * 300,
            initially_expanded=False,
        )
        assert block._detail_built is False
        assert block._detail_container is not None
        assert block._detail_container.content is None

    def test_ensure_detail_built_on_expand(self) -> None:
        block = SubAgentBlock(
            tool_input={
                "subagent_type": "shell",
                "description": "Run tests",
                "prompt": "pytest",
            },
            initially_expanded=False,
        )
        block._ensure_detail_built()
        assert block._detail_built is True
        assert block._detail_container is not None
        assert block._detail_container.content is not None

    def test_initially_expanded_builds_details(self) -> None:
        block = SubAgentBlock(
            tool_input={
                "subagent_type": "generalPurpose",
                "prompt": "hello",
            },
            initially_expanded=True,
        )
        assert block._detail_built is True
        assert block._detail_container is not None
        assert block._detail_container.content is not None
