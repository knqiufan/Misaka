"""
Task management service.

Handles CRUD operations for tasks associated with chat sessions.
"""

from __future__ import annotations

import logging
from typing import Any

from misaka.db.database import DatabaseBackend
from misaka.db.models import TaskItem

logger = logging.getLogger(__name__)


class TaskService:
    """Service for managing session tasks."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db

    def get_by_session(self, session_id: str) -> list[TaskItem]:
        """Get all tasks for a session."""
        return self._db.get_tasks_by_session(session_id)

    def get(self, task_id: str) -> TaskItem | None:
        """Get a task by ID."""
        return self._db.get_task(task_id)

    def create(self, session_id: str, title: str, description: str | None = None) -> TaskItem:
        """Create a new task."""
        task = self._db.create_task(session_id, title, description)
        logger.info("Created task %s: %s", task.id, task.title)
        return task

    def update(self, task_id: str, **kwargs: Any) -> TaskItem | None:
        """Update a task (title, status, description)."""
        return self._db.update_task(task_id, **kwargs)

    def delete(self, task_id: str) -> bool:
        """Delete a task."""
        result = self._db.delete_task(task_id)
        if result:
            logger.info("Deleted task %s", task_id)
        return result
