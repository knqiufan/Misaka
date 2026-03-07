"""
Tests for data models.
"""

from __future__ import annotations

import json

import pytest

from misaka.db.models import (
    ChatSession,
    FilePreview,
    FileTreeNode,
    MCPServerConfig,
    Message,
    MessageContentBlock,
    RouterConfig,
    TaskItem,
    TokenUsage,
)


class TestMessage:

    def test_parse_content_text(self) -> None:
        msg = Message(id="1", session_id="s1", role="user", content="Hello world")
        blocks = msg.parse_content()
        assert len(blocks) == 1
        assert blocks[0].type == "text"
        assert blocks[0].text == "Hello world"

    def test_parse_content_json_array(self) -> None:
        content = json.dumps([
            {"type": "text", "text": "Some text"},
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "a.py"}},
        ])
        msg = Message(id="1", session_id="s1", role="assistant", content=content)
        blocks = msg.parse_content()
        assert len(blocks) == 2
        assert blocks[0].type == "text"
        assert blocks[1].type == "tool_use"
        assert blocks[1].name == "Read"

    def test_parse_content_invalid_json(self) -> None:
        msg = Message(id="1", session_id="s1", role="user", content="{not valid json")
        blocks = msg.parse_content()
        assert len(blocks) == 1
        assert blocks[0].type == "text"
        assert blocks[0].text == "{not valid json"

    def test_parse_content_json_object(self) -> None:
        """JSON object (not array) should be wrapped as text."""
        msg = Message(id="1", session_id="s1", role="user", content='{"key": "value"}')
        blocks = msg.parse_content()
        assert len(blocks) == 1
        assert blocks[0].type == "text"

    def test_parse_content_non_dict_items(self) -> None:
        """Non-dict items in array become text blocks."""
        content = json.dumps(["just a string", 42])
        msg = Message(id="1", session_id="s1", role="user", content=content)
        blocks = msg.parse_content()
        assert len(blocks) == 2
        assert blocks[0].type == "text"
        assert blocks[0].text == "just a string"

    def test_parse_token_usage(self) -> None:
        usage = json.dumps({
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 5,
            "cost_usd": 0.02,
        })
        msg = Message(id="1", session_id="s1", role="assistant", content="hi", token_usage=usage)
        parsed = msg.parse_token_usage()
        assert parsed is not None
        assert parsed.input_tokens == 100
        assert parsed.cost_usd == 0.02

    def test_parse_token_usage_none(self) -> None:
        msg = Message(id="1", session_id="s1", role="user", content="hi")
        assert msg.parse_token_usage() is None

    def test_parse_token_usage_invalid(self) -> None:
        msg = Message(id="1", session_id="s1", role="user", content="hi", token_usage="not json")
        assert msg.parse_token_usage() is None


class TestRouterConfig:

    def test_router_config_defaults(self) -> None:
        config = RouterConfig(id="1", name="Default")
        assert config.api_key == ""
        assert config.base_url == ""
        assert config.config_json == "{}"
        assert config.agent_team is False


class TestFileTreeNode:

    def test_directory_with_children(self) -> None:
        child = FileTreeNode(name="file.txt", path="/tmp/file.txt", type="file")
        parent = FileTreeNode(name="dir", path="/tmp/dir", type="directory", children=[child])
        assert len(parent.children) == 1
        assert parent.children[0].name == "file.txt"

    def test_file_with_extension(self) -> None:
        node = FileTreeNode(name="script.py", path="/tmp/script.py", type="file", extension="py", size=1024)
        assert node.extension == "py"
        assert node.size == 1024


class TestMCPServerConfig:

    def test_default_values(self) -> None:
        config = MCPServerConfig()
        assert config.command == ""
        assert config.args == []
        assert config.env == {}
        assert config.type == "stdio"
        assert config.url == ""

    def test_sse_config(self) -> None:
        config = MCPServerConfig(type="sse", url="http://localhost:3000/mcp")
        assert config.type == "sse"
        assert config.url == "http://localhost:3000/mcp"
