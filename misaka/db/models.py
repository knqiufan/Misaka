"""
Data models for Misaka.

Plain dataclass models representing database entities.
JSON serialization helpers are included for fields that
store structured data as JSON strings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Chat session
# ---------------------------------------------------------------------------

@dataclass
class ChatSession:
    """A chat session (conversation) with Claude."""

    id: str
    title: str = "New Chat"
    model: str = ""
    system_prompt: str = ""
    working_directory: str = ""
    project_name: str = ""
    sdk_session_id: str = ""
    status: Literal["active", "archived"] = "active"
    mode: Literal["code", "plan", "ask"] = "code"
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

@dataclass
class MessageContentBlock:
    """A single content block within a message.

    Mirrors the TypeScript ``MessageContentBlock`` union type.
    The ``type`` field discriminates between text, tool_use,
    tool_result, and code blocks.
    """
    type: str  # "text" | "tool_use" | "tool_result" | "code"
    # Text block fields
    text: str | None = None
    # Tool use fields
    id: str | None = None  # tool_use id
    name: str | None = None
    input: Any = None
    # Tool result fields
    tool_use_id: str | None = None
    content: str | None = None
    is_error: bool = False
    # Code block fields
    language: str | None = None
    code: str | None = None


@dataclass
class Message:
    """A message within a chat session."""

    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str  # JSON string of list[MessageContentBlock] or plain text
    created_at: str = ""
    token_usage: str | None = None  # JSON string of TokenUsage
    # Internal: row ID for cursor-based pagination
    _rowid: int | None = field(default=None, repr=False)

    def parse_content(self) -> list[MessageContentBlock]:
        """Parse the content JSON into a list of content blocks.

        If the content is not valid JSON or not an array, wraps it
        as a single text block.  Unknown dict keys are silently
        dropped so that imported Claude CLI responses don't cause
        TypeError.
        """
        try:
            parsed = json.loads(self.content)
            if isinstance(parsed, list):
                return [self._dict_to_block(b) if isinstance(b, dict)
                        else MessageContentBlock(type="text", text=str(b))
                        for b in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return [MessageContentBlock(type="text", text=self.content)]

    @staticmethod
    def _dict_to_block(raw: dict) -> MessageContentBlock:
        """Convert a dict to MessageContentBlock, tolerating extra keys."""
        _KNOWN = frozenset(MessageContentBlock.__dataclass_fields__)
        filtered = {k: v for k, v in raw.items() if k in _KNOWN}
        if "type" not in filtered:
            filtered["type"] = "text"
            if "text" not in filtered:
                filtered["text"] = json.dumps(raw, ensure_ascii=False)
        return MessageContentBlock(**filtered)

    def parse_token_usage(self) -> TokenUsage | None:
        """Parse the token_usage JSON string."""
        if not self.token_usage:
            return None
        try:
            data = json.loads(self.token_usage)
            return TokenUsage(**data)
        except (json.JSONDecodeError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    """Token usage statistics for a single API call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float | None = None


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@dataclass
class TaskItem:
    """A task associated with a chat session."""

    id: str
    session_id: str
    title: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    description: str | None = None
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# API provider
# ---------------------------------------------------------------------------

@dataclass
class ApiProvider:
    """An API provider configuration."""

    id: str
    name: str
    provider_type: str = "anthropic"
    base_url: str = ""
    api_key: str = ""
    is_active: int = 0  # SQLite boolean: 0 or 1
    sort_order: int = 0
    extra_env: str = "{}"  # JSON string of dict[str, str]
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def parse_extra_env(self) -> dict[str, str]:
        """Parse the extra_env JSON string into a dict."""
        try:
            data = json.loads(self.extra_env)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, str)}
        except (json.JSONDecodeError, TypeError):
            pass
        return {}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class Setting:
    """A key-value setting."""

    key: str
    value: str  # JSON-encoded value


# ---------------------------------------------------------------------------
# File tree
# ---------------------------------------------------------------------------

@dataclass
class FileTreeNode:
    """A node in the file tree (file or directory)."""

    name: str
    path: str
    type: Literal["file", "directory"]
    children: list[FileTreeNode] = field(default_factory=list)
    size: int | None = None
    extension: str | None = None


@dataclass
class FilePreview:
    """Preview content for a file."""

    path: str
    content: str
    language: str
    line_count: int


# ---------------------------------------------------------------------------
# MCP configuration
# ---------------------------------------------------------------------------

@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    type: Literal["stdio", "sse", "http"] = "stdio"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
