"""Unit tests for SubAgentBlock component logic."""

from __future__ import annotations

import pytest

from misaka.ui.chat.components.subagent_block import (
    SubAgentBlock,
    _SUBAGENT_TYPE_META,
    _DEFAULT_ICON,
    _DEFAULT_LABEL,
)


class TestSubAgentBlockMetadata:
    """Tests for metadata extraction and type resolution."""

    def test_extract_all_fields(self):
        block = SubAgentBlock(
            tool_input={
                "subagent_type": "explore",
                "description": "Find files",
                "prompt": "Search for *.py files",
                "model": "claude-4",
            },
        )
        subagent_type, description, prompt, model = block._extract_metadata()
        assert subagent_type == "explore"
        assert description == "Find files"
        assert prompt == "Search for *.py files"
        assert model == "claude-4"

    def test_extract_empty_input(self):
        block = SubAgentBlock(tool_input=None)
        subagent_type, description, prompt, model = block._extract_metadata()
        assert subagent_type == ""
        assert description == ""
        assert prompt == ""
        assert model == ""

    def test_known_type_resolution(self):
        block = SubAgentBlock(tool_input={"subagent_type": "shell"})
        icon, label = block._get_type_meta("shell")
        assert icon is not None
        assert label == "Shell"

    def test_unknown_type_resolution(self):
        block = SubAgentBlock(tool_input={"subagent_type": "custom_agent"})
        icon, label = block._get_type_meta("custom_agent")
        assert icon == _DEFAULT_ICON
        assert label == "custom_agent"

    def test_empty_type_resolution(self):
        block = SubAgentBlock(tool_input={})
        icon, label = block._get_type_meta("")
        assert icon == _DEFAULT_ICON
        assert label == _DEFAULT_LABEL

    def test_all_known_types_have_meta(self):
        expected_types = [
            "generalPurpose", "explore", "shell",
            "code-reviewer", "ci-investigator", "best-of-n-runner",
            "cursor-guide",
        ]
        for agent_type in expected_types:
            assert agent_type in _SUBAGENT_TYPE_META


class TestSubAgentBlockState:
    """Tests for SubAgentBlock display state."""

    def test_initially_collapsed(self):
        block = SubAgentBlock(
            tool_input={"subagent_type": "explore", "description": "test"},
            initially_expanded=False,
        )
        assert block._expanded is False

    def test_initially_expanded(self):
        block = SubAgentBlock(
            tool_input={"subagent_type": "explore"},
            initially_expanded=True,
        )
        assert block._expanded is True

    def test_with_output(self):
        block = SubAgentBlock(
            tool_input={"subagent_type": "shell"},
            tool_output="command completed successfully",
            is_error=False,
        )
        assert block._tool_output == "command completed successfully"
        assert block._is_error is False

    def test_with_error_output(self):
        block = SubAgentBlock(
            tool_input={"subagent_type": "generalPurpose"},
            tool_output="timeout exceeded",
            is_error=True,
        )
        assert block._is_error is True
