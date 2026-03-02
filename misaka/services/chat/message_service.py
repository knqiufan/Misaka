"""
Message handling service.

Manages message persistence, content parsing, and pagination.
"""

from __future__ import annotations

import json
import logging

from misaka.db.database import DatabaseBackend
from misaka.db.models import Message

logger = logging.getLogger(__name__)


class MessageService:
    """Service for managing chat messages."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        before_rowid: int | None = None,
    ) -> tuple[list[Message], bool]:
        """Fetch messages with cursor-based pagination.

        Returns (messages, has_more) where messages are in chronological order.
        """
        return self._db.get_messages(session_id, limit=limit, before_rowid=before_rowid)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str | list[dict],
        token_usage: dict | None = None,
    ) -> Message:
        """Add a message to a session.

        Args:
            session_id: The session to add the message to.
            role: "user" or "assistant".
            content: Either a plain text string or a list of content block dicts
                (will be JSON-serialized).
            token_usage: Optional token usage dict (will be JSON-serialized).
        """
        content_str = json.dumps(content) if isinstance(content, list) else content
        usage_str = json.dumps(token_usage) if token_usage else None
        return self._db.add_message(session_id, role, content_str, usage_str)

    def clear_messages(self, session_id: str) -> None:
        """Delete all messages for a session and reset SDK session ID."""
        self._db.clear_session_messages(session_id)
        logger.info("Cleared messages for session %s", session_id)
