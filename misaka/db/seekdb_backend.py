"""
SeekDB database backend for Misaka.

Uses pyseekdb in embedded mode (Linux only).
Each logical table maps to a SeekDB collection with JSON documents.

NOTE: This module is only imported when pyseekdb is available and the
platform supports embedded mode. On Windows, the SQLite backend is used.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from misaka.db.database import DatabaseBackend
from misaka.db.models import ApiProvider, ChatSession, Message, TaskItem

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _generate_id() -> str:
    return secrets.token_hex(16)


class SeekDBBackend(DatabaseBackend):
    """SeekDB-based persistence backend (embedded mode, Linux only).

    Each table is represented as a SeekDB collection. Documents are
    stored as JSON with metadata for filtering and ordering.
    """

    def __init__(self, db_path: str) -> None:
        import pyseekdb  # noqa: F401  -- fail fast if not installed

        self._db_path = db_path
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import pyseekdb
            self._client = pyseekdb.Client(path=self._db_path, database="misaka")
        return self._client

    def _collection(self, name: str) -> Any:
        """Get or create a named collection."""
        return self._get_client().get_or_create_collection(name)

    # ----- Lifecycle -----

    def initialize(self) -> None:
        client = self._get_client()
        for name in ["chat_sessions", "messages", "settings", "tasks", "api_providers"]:
            try:
                client.get_or_create_collection(name)
            except Exception as exc:
                logger.warning("Failed to create collection %s: %s", name, exc)

    def close(self) -> None:
        self._client = None

    # ----- Sessions -----

    def get_all_sessions(self) -> list[ChatSession]:
        col = self._collection("chat_sessions")
        try:
            results = col.get()
            if not results or not results.get("documents"):
                return []

            sessions = []
            for doc_str in results["documents"]:
                doc = json.loads(doc_str) if isinstance(doc_str, str) else doc_str
                sessions.append(self._doc_to_session(doc))

            sessions.sort(key=lambda s: s.updated_at or s.created_at, reverse=True)
            return sessions
        except Exception as exc:
            logger.error("SeekDB get_all_sessions error: %s", exc)
            return []

    def get_session(self, session_id: str) -> ChatSession | None:
        col = self._collection("chat_sessions")
        try:
            results = col.get(ids=[session_id])
            if results and results.get("documents") and results["documents"]:
                doc = json.loads(results["documents"][0]) if isinstance(results["documents"][0], str) else results["documents"][0]
                return self._doc_to_session(doc)
        except Exception as exc:
            logger.error("SeekDB get_session error: %s", exc)
        return None

    def create_session(
        self,
        title: str = "New Chat",
        model: str = "",
        system_prompt: str = "",
        working_directory: str = "",
        mode: str = "code",
    ) -> ChatSession:
        col = self._collection("chat_sessions")
        session_id = _generate_id()
        now = _now()

        project_name = ""
        if working_directory:
            project_name = Path(working_directory).name

        doc = {
            "id": session_id,
            "title": title,
            "model": model,
            "system_prompt": system_prompt,
            "working_directory": working_directory,
            "project_name": project_name,
            "sdk_session_id": "",
            "status": "active",
            "mode": mode,
            "created_at": now,
            "updated_at": now,
        }

        col.add(ids=[session_id], documents=[json.dumps(doc)])
        return self._doc_to_session(doc)

    def update_session_title(self, session_id: str, title: str) -> None:
        self._update_session_field(session_id, "title", title)

    def update_session_timestamp(self, session_id: str) -> None:
        self._update_session_field(session_id, "updated_at", _now())

    def update_sdk_session_id(self, session_id: str, sdk_session_id: str) -> None:
        self._update_session_field(session_id, "sdk_session_id", sdk_session_id)

    def update_session_working_directory(self, session_id: str, working_directory: str) -> None:
        session = self.get_session(session_id)
        if session:
            project_name = Path(working_directory).name if working_directory else ""
            doc = self._session_to_doc(session)
            doc["working_directory"] = working_directory
            doc["project_name"] = project_name
            doc["updated_at"] = _now()
            col = self._collection("chat_sessions")
            col.update(ids=[session_id], documents=[json.dumps(doc)])

    def update_session_mode(self, session_id: str, mode: str) -> None:
        self._update_session_field(session_id, "mode", mode)

    def update_session_model(self, session_id: str, model: str) -> None:
        self._update_session_field(session_id, "model", model)

    def update_session_status(self, session_id: str, status: str) -> None:
        self._update_session_field(session_id, "status", status)

    def delete_session(self, session_id: str) -> bool:
        try:
            # Delete associated messages and tasks
            self._delete_by_field("messages", "session_id", session_id)
            self._delete_by_field("tasks", "session_id", session_id)

            col = self._collection("chat_sessions")
            col.delete(ids=[session_id])
            return True
        except Exception as exc:
            logger.error("SeekDB delete_session error: %s", exc)
            return False

    def _update_session_field(self, session_id: str, field: str, value: Any) -> None:
        """Update a single field on a session document."""
        session = self.get_session(session_id)
        if not session:
            return
        doc = self._session_to_doc(session)
        doc[field] = value
        if field != "updated_at":
            doc["updated_at"] = _now()
        col = self._collection("chat_sessions")
        col.update(ids=[session_id], documents=[json.dumps(doc)])

    def _delete_by_field(self, collection_name: str, field: str, value: str) -> None:
        """Delete all documents in a collection where field matches value."""
        col = self._collection(collection_name)
        try:
            results = col.get()
            if not results or not results.get("documents"):
                return
            ids_to_delete = []
            for i, doc_str in enumerate(results["documents"]):
                doc = json.loads(doc_str) if isinstance(doc_str, str) else doc_str
                if doc.get(field) == value:
                    ids_to_delete.append(results["ids"][i])
            if ids_to_delete:
                col.delete(ids=ids_to_delete)
        except Exception as exc:
            logger.warning("SeekDB _delete_by_field error on %s: %s", collection_name, exc)

    @staticmethod
    def _doc_to_session(doc: dict[str, Any]) -> ChatSession:
        return ChatSession(
            id=doc.get("id", ""),
            title=doc.get("title", "New Chat"),
            model=doc.get("model", ""),
            system_prompt=doc.get("system_prompt", ""),
            working_directory=doc.get("working_directory", ""),
            project_name=doc.get("project_name", ""),
            sdk_session_id=doc.get("sdk_session_id", ""),
            status=doc.get("status", "active"),
            mode=doc.get("mode", "code"),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        )

    @staticmethod
    def _session_to_doc(session: ChatSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "title": session.title,
            "model": session.model,
            "system_prompt": session.system_prompt,
            "working_directory": session.working_directory,
            "project_name": session.project_name,
            "sdk_session_id": session.sdk_session_id,
            "status": session.status,
            "mode": session.mode,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    # ----- Messages -----

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        before_rowid: int | None = None,
    ) -> tuple[list[Message], bool]:
        col = self._collection("messages")
        try:
            results = col.get()
            if not results or not results.get("documents"):
                return [], False

            messages = []
            for i, doc_str in enumerate(results["documents"]):
                doc = json.loads(doc_str) if isinstance(doc_str, str) else doc_str
                if doc.get("session_id") == session_id:
                    msg = self._doc_to_message(doc, rowid=i + 1)
                    messages.append(msg)

            # Sort by created_at
            messages.sort(key=lambda m: m.created_at)

            # Apply cursor-based pagination
            if before_rowid is not None:
                messages = [m for m in messages if (m._rowid or 0) < before_rowid]

            has_more = len(messages) > limit
            if has_more:
                messages = messages[-limit:]

            return messages, has_more
        except Exception as exc:
            logger.error("SeekDB get_messages error: %s", exc)
            return [], False

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_usage: str | None = None,
    ) -> Message:
        col = self._collection("messages")
        msg_id = _generate_id()
        now = _now()

        doc = {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "token_usage": token_usage,
            "created_at": now,
        }

        col.add(ids=[msg_id], documents=[json.dumps(doc)])

        # Update session timestamp
        self.update_session_timestamp(session_id)

        return Message(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            token_usage=token_usage,
            created_at=now,
        )

    def clear_session_messages(self, session_id: str) -> None:
        self._delete_by_field("messages", "session_id", session_id)
        self._update_session_field(session_id, "sdk_session_id", "")

    @staticmethod
    def _doc_to_message(doc: dict[str, Any], rowid: int = 0) -> Message:
        msg = Message(
            id=doc.get("id", ""),
            session_id=doc.get("session_id", ""),
            role=doc.get("role", "user"),
            content=doc.get("content", ""),
            token_usage=doc.get("token_usage"),
            created_at=doc.get("created_at", ""),
        )
        msg._rowid = rowid
        return msg

    # ----- Settings -----

    def get_setting(self, key: str) -> str | None:
        col = self._collection("settings")
        try:
            results = col.get(ids=[key])
            if results and results.get("documents") and results["documents"]:
                doc = json.loads(results["documents"][0]) if isinstance(results["documents"][0], str) else results["documents"][0]
                return doc.get("value")
        except Exception:
            pass
        return None

    def set_setting(self, key: str, value: str) -> None:
        col = self._collection("settings")
        doc = json.dumps({"key": key, "value": value})
        try:
            existing = col.get(ids=[key])
            if existing and existing.get("documents") and existing["documents"]:
                col.update(ids=[key], documents=[doc])
            else:
                col.add(ids=[key], documents=[doc])
        except Exception as exc:
            logger.error("SeekDB set_setting error: %s", exc)

    def get_all_settings(self) -> dict[str, str]:
        col = self._collection("settings")
        try:
            results = col.get()
            if not results or not results.get("documents"):
                return {}
            settings: dict[str, str] = {}
            for doc_str in results["documents"]:
                doc = json.loads(doc_str) if isinstance(doc_str, str) else doc_str
                key = doc.get("key", "")
                value = doc.get("value", "")
                if key:
                    settings[key] = value
            return settings
        except Exception as exc:
            logger.error("SeekDB get_all_settings error: %s", exc)
            return {}

    # ----- Tasks -----

    def get_tasks_by_session(self, session_id: str) -> list[TaskItem]:
        col = self._collection("tasks")
        try:
            results = col.get()
            if not results or not results.get("documents"):
                return []
            tasks = []
            for doc_str in results["documents"]:
                doc = json.loads(doc_str) if isinstance(doc_str, str) else doc_str
                if doc.get("session_id") == session_id:
                    tasks.append(self._doc_to_task(doc))
            tasks.sort(key=lambda t: t.created_at)
            return tasks
        except Exception as exc:
            logger.error("SeekDB get_tasks_by_session error: %s", exc)
            return []

    def get_task(self, task_id: str) -> TaskItem | None:
        col = self._collection("tasks")
        try:
            results = col.get(ids=[task_id])
            if results and results.get("documents") and results["documents"]:
                doc = json.loads(results["documents"][0]) if isinstance(results["documents"][0], str) else results["documents"][0]
                return self._doc_to_task(doc)
        except Exception:
            pass
        return None

    def create_task(self, session_id: str, title: str, description: str | None = None) -> TaskItem:
        col = self._collection("tasks")
        task_id = _generate_id()
        now = _now()

        doc = {
            "id": task_id,
            "session_id": session_id,
            "title": title,
            "status": "pending",
            "description": description or "",
            "created_at": now,
            "updated_at": now,
        }

        col.add(ids=[task_id], documents=[json.dumps(doc)])
        return self._doc_to_task(doc)

    def update_task(self, task_id: str, **kwargs: Any) -> TaskItem | None:
        task = self.get_task(task_id)
        if not task:
            return None

        doc = self._task_to_doc(task)
        for key, value in kwargs.items():
            if key in doc:
                doc[key] = value
        doc["updated_at"] = _now()

        col = self._collection("tasks")
        col.update(ids=[task_id], documents=[json.dumps(doc)])
        return self._doc_to_task(doc)

    def delete_task(self, task_id: str) -> bool:
        col = self._collection("tasks")
        try:
            col.delete(ids=[task_id])
            return True
        except Exception:
            return False

    @staticmethod
    def _doc_to_task(doc: dict[str, Any]) -> TaskItem:
        return TaskItem(
            id=doc.get("id", ""),
            session_id=doc.get("session_id", ""),
            title=doc.get("title", ""),
            status=doc.get("status", "pending"),
            description=doc.get("description"),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        )

    @staticmethod
    def _task_to_doc(task: TaskItem) -> dict[str, Any]:
        return {
            "id": task.id,
            "session_id": task.session_id,
            "title": task.title,
            "status": task.status,
            "description": task.description or "",
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    # ----- API Providers -----

    def get_all_providers(self) -> list[ApiProvider]:
        col = self._collection("api_providers")
        try:
            results = col.get()
            if not results or not results.get("documents"):
                return []
            providers = []
            for doc_str in results["documents"]:
                doc = json.loads(doc_str) if isinstance(doc_str, str) else doc_str
                providers.append(self._doc_to_provider(doc))
            providers.sort(key=lambda p: p.sort_order)
            return providers
        except Exception as exc:
            logger.error("SeekDB get_all_providers error: %s", exc)
            return []

    def get_provider(self, provider_id: str) -> ApiProvider | None:
        col = self._collection("api_providers")
        try:
            results = col.get(ids=[provider_id])
            if results and results.get("documents") and results["documents"]:
                doc = json.loads(results["documents"][0]) if isinstance(results["documents"][0], str) else results["documents"][0]
                return self._doc_to_provider(doc)
        except Exception:
            pass
        return None

    def get_active_provider(self) -> ApiProvider | None:
        providers = self.get_all_providers()
        for p in providers:
            if p.is_active:
                return p
        return None

    def create_provider(self, name: str, **kwargs: Any) -> ApiProvider:
        col = self._collection("api_providers")
        provider_id = _generate_id()
        now = _now()

        doc = {
            "id": provider_id,
            "name": name,
            "provider_type": kwargs.get("provider_type", "anthropic"),
            "base_url": kwargs.get("base_url", ""),
            "api_key": kwargs.get("api_key", ""),
            "is_active": kwargs.get("is_active", 0),
            "sort_order": kwargs.get("sort_order", 0),
            "extra_env": kwargs.get("extra_env", "{}"),
            "notes": kwargs.get("notes", ""),
            "created_at": now,
            "updated_at": now,
        }

        col.add(ids=[provider_id], documents=[json.dumps(doc)])
        return self._doc_to_provider(doc)

    def update_provider(self, provider_id: str, **kwargs: Any) -> ApiProvider | None:
        provider = self.get_provider(provider_id)
        if not provider:
            return None

        doc = self._provider_to_doc(provider)
        for key, value in kwargs.items():
            if key in doc:
                doc[key] = value
        doc["updated_at"] = _now()

        col = self._collection("api_providers")
        col.update(ids=[provider_id], documents=[json.dumps(doc)])
        return self._doc_to_provider(doc)

    def delete_provider(self, provider_id: str) -> bool:
        col = self._collection("api_providers")
        try:
            col.delete(ids=[provider_id])
            return True
        except Exception:
            return False

    def activate_provider(self, provider_id: str) -> bool:
        self.deactivate_all_providers()
        provider = self.get_provider(provider_id)
        if not provider:
            return False
        self.update_provider(provider_id, is_active=1)
        return True

    def deactivate_all_providers(self) -> None:
        providers = self.get_all_providers()
        for p in providers:
            if p.is_active:
                self.update_provider(p.id, is_active=0)

    @staticmethod
    def _doc_to_provider(doc: dict[str, Any]) -> ApiProvider:
        return ApiProvider(
            id=doc.get("id", ""),
            name=doc.get("name", ""),
            provider_type=doc.get("provider_type", "anthropic"),
            base_url=doc.get("base_url", ""),
            api_key=doc.get("api_key", ""),
            is_active=doc.get("is_active", 0),
            sort_order=doc.get("sort_order", 0),
            extra_env=doc.get("extra_env", "{}"),
            notes=doc.get("notes", ""),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        )

    @staticmethod
    def _provider_to_doc(provider: ApiProvider) -> dict[str, Any]:
        return {
            "id": provider.id,
            "name": provider.name,
            "provider_type": provider.provider_type,
            "base_url": provider.base_url,
            "api_key": provider.api_key,
            "is_active": provider.is_active,
            "sort_order": provider.sort_order,
            "extra_env": provider.extra_env,
            "notes": provider.notes,
            "created_at": provider.created_at,
            "updated_at": provider.updated_at,
        }
