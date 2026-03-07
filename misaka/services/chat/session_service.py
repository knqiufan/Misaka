"""
Session management service.

Handles CRUD operations for chat sessions with state synchronization.
"""

from __future__ import annotations

import logging

from misaka.db.database import DatabaseBackend
from misaka.db.models import ChatSession

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing chat sessions."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db

    def get_all(self) -> list[ChatSession]:
        """Return all sessions, ordered by most recently updated."""
        return self._db.get_all_sessions()

    def get(self, session_id: str) -> ChatSession | None:
        """Return a session by ID."""
        return self._db.get_session(session_id)

    def create(
        self,
        title: str = "New Chat",
        model: str = "",
        system_prompt: str = "",
        working_directory: str = "",
        mode: str = "code",
    ) -> ChatSession:
        """Create a new chat session."""
        session = self._db.create_session(
            title=title,
            model=model,
            system_prompt=system_prompt,
            working_directory=working_directory,
            mode=mode,
        )
        logger.info("Created session %s: %s", session.id, session.title)
        return session

    def update_title(self, session_id: str, title: str) -> None:
        """Update a session's title."""
        self._db.update_session_title(session_id, title)

    def update_working_directory(self, session_id: str, working_directory: str) -> None:
        """Update a session's working directory."""
        self._db.update_session_working_directory(session_id, working_directory)

    def update_mode(self, session_id: str, mode: str) -> None:
        """Update a session's mode (code/plan/ask)."""
        self._db.update_session_mode(session_id, mode)

    def update_model(self, session_id: str, model: str) -> None:
        """Update a session's model."""
        self._db.update_session_model(session_id, model)

    def update_status(self, session_id: str, status: str) -> None:
        """Archive or reactivate a session."""
        self._db.update_session_status(session_id, status)

    def update_sdk_session_id(self, session_id: str, sdk_session_id: str) -> None:
        """Store the SDK session ID for conversation resume."""
        self._db.update_sdk_session_id(session_id, sdk_session_id)

    def delete(self, session_id: str, image_service: Any = None) -> bool:
        """Delete a session and all its messages/tasks.

        Args:
            session_id: The session ID to delete.
            image_service: Optional ImageService to clean up attachments.
        """
        result = self._db.delete_session(session_id)
        if result:
            logger.info("Deleted session %s", session_id)
            # Clean up image attachments
            if image_service:
                image_service.cleanup_session_images(session_id)
        return result
