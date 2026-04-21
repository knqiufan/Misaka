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
    status: Literal["active", "archived", "hidden"] = "active"
    mode: Literal["agent", "plan", "ask"] = "agent"
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
    tool_result, code, and image blocks.
    """
    type: str  # "text" | "thinking" | "tool_use" | "tool_result" | "code" | "image"
    # Text block fields
    text: str | None = None
    # Thinking block fields
    thinking: str | None = None
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
    # Image block fields
    source_type: str | None = None  # "file" | "base64" | "url"
    file_path: str | None = None
    url: str | None = None
    media_type: str | None = None  # "image/png", "image/jpeg", etc.
    alt_text: str | None = None
    # Base64 data for inline images (not persisted to DB)
    base64_data: str | None = None


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
        known = frozenset(MessageContentBlock.__dataclass_fields__)
        filtered = {k: v for k, v in raw.items() if k in known}
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
# Image attachments
# ---------------------------------------------------------------------------

@dataclass
class ImageAttachment:
    """Metadata for a persisted image attachment."""

    id: str
    file_path: str  # Path in ~/.misaka/attachments/
    original_name: str
    mime_type: str  # image/png, image/jpeg, etc.
    size_bytes: int
    width: int | None = None
    height: int | None = None
    thumbnail_path: str | None = None
    created_at: str = ""


@dataclass
class PendingImage:
    """In-memory image waiting to be sent (not yet persisted)."""

    id: str
    temp_path: str  # Temporary file path
    thumbnail: bytes  # Thumbnail image data (for preview)
    original_name: str
    mime_type: str
    size_bytes: int = 0
    width: int | None = None
    height: int | None = None


# ---------------------------------------------------------------------------
# Router configuration
# ---------------------------------------------------------------------------

@dataclass
class RouterConfig:
    """A Claude Code Router configuration."""

    id: str
    name: str
    api_key: str = ""
    base_url: str = ""
    main_model: str = ""
    haiku_model: str = ""
    opus_model: str = ""
    sonnet_model: str = ""
    agent_team: bool = False
    config_json: str = "{}"
    is_active: int = 0
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Notification (in-memory only, not persisted to DB)
# ---------------------------------------------------------------------------

@dataclass
class Notification:
    """An application notification (stored in memory, not in the database)."""

    id: str
    type: Literal["info", "success", "warning", "error"]
    title: str
    message: str
    timestamp: str  # ISO UTC
    read: bool = False
    source: str = ""  # "stream", "permission", "update", "mcp", "system"
    session_id: str | None = None
    action_label: str | None = None
    action_data: dict[str, Any] | None = None


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
