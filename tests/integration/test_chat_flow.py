"""
Integration test: chat flow.

Tests the full chat flow from session creation through message persistence.
"""

from __future__ import annotations

import pytest

from misaka.db.database import DatabaseBackend
from misaka.services.message_service import MessageService
from misaka.services.session_service import SessionService


class TestChatFlow:

    def test_create_session_send_messages(self, db: DatabaseBackend) -> None:
        session_svc = SessionService(db)
        message_svc = MessageService(db)

        # Create a session
        session = session_svc.create(title="Test Chat", working_directory="/tmp/test")
        assert session.id

        # Add messages
        msg1 = message_svc.add_message(session.id, "user", "Hello Claude")
        msg2 = message_svc.add_message(session.id, "assistant", "Hello! How can I help?")

        # Retrieve messages
        messages, has_more = message_svc.get_messages(session.id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert has_more is False

        # Clear messages
        message_svc.clear_messages(session.id)
        messages, _ = message_svc.get_messages(session.id)
        assert len(messages) == 0

    def test_structured_content(self, db: DatabaseBackend) -> None:
        session_svc = SessionService(db)
        message_svc = MessageService(db)

        session = session_svc.create(title="Test")
        content_blocks = [
            {"type": "text", "text": "Let me help you."},
            {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "a.py"}},
        ]
        msg = message_svc.add_message(session.id, "assistant", content_blocks)

        # Retrieve and parse
        messages, _ = message_svc.get_messages(session.id)
        assert len(messages) == 1
        blocks = messages[0].parse_content()
        assert len(blocks) == 2
        assert blocks[0].type == "text"
        assert blocks[1].type == "tool_use"
        assert blocks[1].name == "Read"
