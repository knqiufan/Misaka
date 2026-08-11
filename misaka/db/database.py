"""
Database abstraction layer for Misaka.

Defines the ``DatabaseBackend`` abstract base class and a factory function
that selects the appropriate backend based on platform.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import Any

from misaka.db.models import (
    ChatSession,
    KBChunk,
    KBCleanupJob,
    KBDocument,
    KnowledgeBase,
    Message,
    ModelInfo,
    RouterConfig,
    RouterModel,
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

    # ----- Transactions -----

    @abstractmethod
    def transaction(self) -> AbstractContextManager[None]:
        """Context manager for batching multiple operations in a single transaction.

        Usage::

            with db.transaction():
                db.update_session_title(...)
                db.update_sdk_session_id(...)
                db.add_message(...)

        All operations inside the block are committed atomically at exit.
        On exception the transaction is rolled back.
        """

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
    def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_usage: str | None = None,
    ) -> Message:
        """Create a Message object without writing to the database.

        Used for optimistic UI display — the message can be shown
        immediately and persisted later via ``add_message_from_model()``.
        """

    @abstractmethod
    def add_message_from_model(self, message: Message) -> None:
        """Persist an already-created Message object to the database.

        Counterpart to ``create_message()`` for deferred writes.
        """

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

    # ----- SeekDB Configuration -----

    @abstractmethod
    def get_seekdb_config(self) -> dict[str, Any] | None:
        """Return the singleton SeekDB remote connection configuration."""

    @abstractmethod
    def save_seekdb_config(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database_name: str,
    ) -> None:
        """Insert or update the singleton SeekDB remote connection configuration."""

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

    # ----- Router Models -----

    @abstractmethod
    def save_router_models(
        self,
        config_id: str,
        models: list[dict[str, Any]],
    ) -> None:
        """Replace all detected models for a router config.

        Each dict in *models* must contain ``model_id`` and ``model_type``.
        Existing models for *config_id* are deleted first.
        """

    @abstractmethod
    def get_router_models(self, config_id: str) -> list[RouterModel]:
        """Return all models detected under a router config."""

    @abstractmethod
    def update_router_model_selection(self, model_id: str, is_selected: bool) -> None:
        """Toggle selection state of a detected model."""

    @abstractmethod
    def delete_router_models_by_config(self, config_id: str) -> None:
        """Delete all detected models for a router config."""

    @abstractmethod
    def get_all_selected_models_by_type(
        self,
        model_type: str,
    ) -> list[ModelInfo]:
        """Return selected models of a given type across all router configs.

        Performs a JOIN with ``router_configs`` to include ``base_url``
        and ``api_key`` in the returned :class:`ModelInfo` objects.
        """

    # ----- Knowledge Bases -----

    @abstractmethod
    def create_knowledge_base(self, kb: KnowledgeBase) -> None:
        """Insert a new knowledge base record."""

    @abstractmethod
    def get_knowledge_base(self, kb_id: str) -> KnowledgeBase | None:
        """Return a knowledge base by ID, or None."""

    @abstractmethod
    def get_all_knowledge_bases(self) -> list[KnowledgeBase]:
        """Return all knowledge bases ordered by updated_at descending."""

    @abstractmethod
    def update_knowledge_base(self, kb_id: str, **kwargs: Any) -> None:
        """Update knowledge base fields. Only provided kwargs are changed."""

    @abstractmethod
    def delete_knowledge_base(self, kb_id: str) -> None:
        """Delete a knowledge base and cascade-delete its documents and chunks."""

    # ----- KB Documents -----

    @abstractmethod
    def create_kb_document(self, doc: KBDocument) -> None:
        """Insert a new knowledge base document record."""

    @abstractmethod
    def get_kb_document(self, doc_id: str) -> KBDocument | None:
        """Return a KB document by ID, or None."""

    @abstractmethod
    def get_kb_documents_by_kb(self, kb_id: str) -> list[KBDocument]:
        """Return all documents belonging to a knowledge base."""

    @abstractmethod
    def update_kb_document(self, doc_id: str, **kwargs: Any) -> None:
        """Update document fields. Only provided kwargs are changed."""

    @abstractmethod
    def delete_kb_document(self, doc_id: str) -> None:
        """Delete a document and cascade-delete its chunks."""

    @abstractmethod
    def get_kb_document_by_hash(self, kb_id: str, file_hash: str) -> KBDocument | None:
        """Find an existing document with the same content hash (dedup)."""

    # ----- KB Chunks -----

    @abstractmethod
    def create_kb_chunks_batch(self, chunks: list[KBChunk]) -> None:
        """Bulk-insert text chunks for a document."""

    @abstractmethod
    def get_kb_chunks_by_document(self, doc_id: str) -> list[KBChunk]:
        """Return all chunks for a specific document, ordered by chunk_index."""

    @abstractmethod
    def get_kb_chunks_by_kb(self, kb_id: str) -> list[KBChunk]:
        """Return all chunks for a knowledge base, ordered by chunk_index."""

    @abstractmethod
    def get_kb_chunks_by_index(
        self, kb_id: str, index_version: str,
    ) -> list[KBChunk]:
        """Return chunks belonging to one immutable KB index version."""

    @abstractmethod
    def activate_kb_index(
        self,
        kb_id: str,
        index_version: str,
        chunks: list[KBChunk],
        document_updates: dict[str, dict[str, Any]],
        dimensions: int,
    ) -> None:
        """Atomically publish staged chunks and their corresponding document state."""

    @abstractmethod
    def delete_kb_chunks_by_index(self, kb_id: str, index_version: str) -> None:
        """Remove persisted chunks belonging to a retired index version."""

    @abstractmethod
    def delete_kb_chunks_by_document(self, doc_id: str) -> None:
        """Delete all chunks belonging to a specific document."""

    @abstractmethod
    def update_kb_chunk_embedded(self, chunk_ids: list[str]) -> None:
        """Mark chunks as embedded (``is_embedded = 1``)."""

    # ----- KB background jobs and durable cleanup -----

    @abstractmethod
    def create_kb_job(self, kb_id: str, document_id: str, operation: str) -> str:
        """Create and return a durable KB operation record."""

    @abstractmethod
    def update_kb_job(self, job_id: str, status: str, error_message: str = "") -> None:
        """Update a KB operation record."""

    @abstractmethod
    def create_kb_cleanup_job(
        self, kb_id: str, index_version: str, operation: str, error_message: str,
    ) -> str:
        """Persist vector cleanup that must be retried."""

    @abstractmethod
    def get_pending_kb_cleanup_jobs(self) -> list[KBCleanupJob]:
        """Return all cleanup jobs still awaiting successful vector deletion."""

    @abstractmethod
    def update_kb_cleanup_job(
        self, job_id: str, status: str, error_message: str = "",
    ) -> None:
        """Record a cleanup attempt or completion."""

    # ----- Dashboard aggregation -----

    @abstractmethod
    def get_session_counts(self) -> dict[str, int]:
        """Return session and message counts for dashboard.

        Expected keys: total, active, archived, messages.
        """

    @abstractmethod
    def get_token_usage_rows(self) -> list[str]:
        """Return raw token_usage JSON strings for all assistant messages."""

    @abstractmethod
    def get_daily_token_usage_rows(self, days: int = 30) -> list[tuple[str, str]]:
        """Return ``(date, token_usage_json)`` pairs for the last *days* days.

        Each row represents one assistant message with a non-null token_usage,
        grouped by ``DATE(created_at)`` is left to the caller; the backend
        returns individual rows so the service layer can aggregate flexibly.
        """


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
