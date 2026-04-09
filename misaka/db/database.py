"""
Database abstraction layer for Misaka.

Defines the ``DatabaseBackend`` abstract base class and a factory function
that selects the appropriate backend based on platform.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from misaka.db.models import (
    ChatSession,
    Message,
    RouterConfig,
    TaskItem,
)

logger = logging.getLogger(__name__)


class DatabaseBackend(ABC):
    """Abstract interface for database operations.

    All CRUD operations required by the application are declared here.
    Primary implementation: :class:`~misaka.db.sqlite_backend.SQLiteBackend`.
    """

    # ----- Lifecycle -----

    @abstractmethod
    def initialize(self) -> None:
        """Create tables/collections and run migrations."""

    @abstractmethod
    def close(self) -> None:
        """Close the database connection gracefully."""

    # ----- Sessions -----

    @abstractmethod
    def get_all_sessions(self) -> list[ChatSession]:
        """Return all sessions ordered by updated_at descending."""

    @abstractmethod
    def get_session(self, session_id: str) -> ChatSession | None:
        """Return a single session by ID, or None."""

    @abstractmethod
    def get_session_by_sdk_id(self, sdk_session_id: str) -> ChatSession | None:
        """Return a session matching the given SDK session ID, or None."""

    @abstractmethod
    def create_session(
        self,
        title: str = "New Chat",
        model: str = "",
        system_prompt: str = "",
        working_directory: str = "",
        mode: str = "agent",
    ) -> ChatSession:
        """Create and return a new chat session."""

    @abstractmethod
    def update_session_title(self, session_id: str, title: str) -> None:
        """Update a session's title."""

    @abstractmethod
    def update_session_timestamp(self, session_id: str) -> None:
        """Touch the session's updated_at to now."""

    @abstractmethod
    def update_sdk_session_id(self, session_id: str, sdk_session_id: str) -> None:
        """Store the Claude SDK session ID for resume."""

    @abstractmethod
    def update_session_working_directory(self, session_id: str, working_directory: str) -> None:
        """Update the session's working directory and project name."""

    @abstractmethod
    def update_session_mode(self, session_id: str, mode: str) -> None:
        """Update the session's mode (agent/plan/ask)."""

    @abstractmethod
    def update_session_model(self, session_id: str, model: str) -> None:
        """Update the session's model identifier."""

    @abstractmethod
    def update_session_status(self, session_id: str, status: str) -> None:
        """Update the session's status (active/archived)."""

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages/tasks. Return True if deleted."""

    # ----- Messages -----

    @abstractmethod
    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        before_rowid: int | None = None,
    ) -> tuple[list[Message], bool]:
        """Return messages for a session with cursor-based pagination.

        Returns ``(messages, has_more)`` where messages are in chronological
        order and ``has_more`` indicates whether older messages exist.
        """

    @abstractmethod
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_usage: str | None = None,
    ) -> Message:
        """Insert a message and update the session timestamp."""

    @abstractmethod
    def add_messages_batch(
        self,
        session_id: str,
        messages: list[dict[str, str | None]],
    ) -> None:
        """Insert multiple messages in a single transaction."""

    @abstractmethod
    def clear_session_messages(self, session_id: str) -> None:
        """Delete all messages for a session and reset its SDK session ID."""

    @abstractmethod
    def delete_message(self, message_id: str) -> bool:
        """Delete a message by ID. Return True if deleted."""

    # ----- Settings -----

    @abstractmethod
    def get_setting(self, key: str) -> str | None:
        """Return a setting value by key, or None."""

    @abstractmethod
    def set_setting(self, key: str, value: str) -> None:
        """Insert or update a setting."""

    @abstractmethod
    def get_all_settings(self) -> dict[str, str]:
        """Return all settings as a dict."""

    # ----- Tasks -----

    @abstractmethod
    def get_tasks_by_session(self, session_id: str) -> list[TaskItem]:
        """Return tasks for a session ordered by created_at ascending."""

    @abstractmethod
    def get_task(self, task_id: str) -> TaskItem | None:
        """Return a task by ID, or None."""

    @abstractmethod
    def create_task(self, session_id: str, title: str, description: str | None = None) -> TaskItem:
        """Create and return a new task."""

    @abstractmethod
    def update_task(self, task_id: str, **kwargs: Any) -> TaskItem | None:
        """Update task fields (title, status, description). Return updated task."""

    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        """Delete a task. Return True if deleted."""

    # ----- Router Configs -----

    @abstractmethod
    def get_all_router_configs(self) -> list[RouterConfig]:
        """Return all router configs ordered by sort_order."""

    @abstractmethod
    def get_router_config(self, config_id: str) -> RouterConfig | None:
        """Return a router config by ID, or None."""

    @abstractmethod
    def get_active_router_config(self) -> RouterConfig | None:
        """Return the currently active router config, or None."""

    @abstractmethod
    def create_router_config(self, name: str, **kwargs: Any) -> RouterConfig:
        """Create and return a new router config."""

    @abstractmethod
    def update_router_config(self, config_id: str, **kwargs: Any) -> RouterConfig | None:
        """Update router config fields. Return updated config."""

    @abstractmethod
    def delete_router_config(self, config_id: str) -> bool:
        """Delete a router config. Return True if deleted."""

    @abstractmethod
    def activate_router_config(self, config_id: str) -> bool:
        """Set a router config as active (deactivating all others). Return True if found."""

    # ----- Dashboard aggregation -----

    @abstractmethod
    def get_session_counts(self) -> dict[str, int]:
        """Return session and message counts for dashboard.

        Expected keys: total, active, archived, messages.
        """

    @abstractmethod
    def get_token_usage_rows(self) -> list[str]:
        """Return raw token_usage JSON strings for all assistant messages."""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_database(db_path: str | None = None) -> DatabaseBackend:
    """Create the SQLite database backend.

    Args:
        db_path: Override path to the database file. If None, uses the
            default from :mod:`misaka.config`.
    """
    from misaka.config import DB_PATH

    path = db_path or str(DB_PATH)

    from misaka.db.sqlite_backend import SQLiteBackend
    logger.info("Using SQLite backend at %s", path)
    return SQLiteBackend(path)
