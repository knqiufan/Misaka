"""Knowledge base lifecycle management service."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from typing import TYPE_CHECKING, Any

from misaka.config import SettingKeys, get_kb_storage_dir
from misaka.db.models import KnowledgeBase
from misaka.services.knowledge.index_fingerprint import build_index_fingerprint
from misaka.services.knowledge.index_manager import KBIndexManager
from misaka.services.knowledge.job_coordinator import KnowledgeBaseJobCoordinator

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.services.knowledge.rag_orchestrator import RAGOrchestrator

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """CRUD, statistics, and chat-selection helpers for knowledge bases."""

    def __init__(
        self,
        db: DatabaseBackend,
        orchestrator: RAGOrchestrator | None = None,
        coordinator: KnowledgeBaseJobCoordinator | None = None,
    ) -> None:
        self._db = db
        self._orchestrator = orchestrator
        self._coordinator = coordinator or KnowledgeBaseJobCoordinator(db)
        self._index_manager = (
            KBIndexManager(db, orchestrator) if orchestrator is not None else None
        )

    # ── Queries ───────────────────────────────────────────────────────

    def get_all(self) -> list[KnowledgeBase]:
        return self._db.get_all_knowledge_bases()

    def get(self, kb_id: str) -> KnowledgeBase | None:
        return self._db.get_knowledge_base(kb_id)

    # ── Mutations ─────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        description: str = "",
        embedding_model_id: str = "",
        embedding_router_config_id: str = "",
        reranker_model_id: str = "",
        reranker_router_config_id: str = "",
        **kwargs: Any,
    ) -> KnowledgeBase:
        kb = KnowledgeBase(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            embedding_model_id=embedding_model_id,
            embedding_router_config_id=embedding_router_config_id,
            reranker_model_id=reranker_model_id,
            reranker_router_config_id=reranker_router_config_id,
            chunk_size=kwargs.get("chunk_size", 512),
            chunk_overlap=kwargs.get("chunk_overlap", 64),
            top_k=kwargs.get("top_k", 5),
            similarity_threshold=kwargs.get("similarity_threshold", 0.0),
            reranker_top_k=kwargs.get("reranker_top_k", 3),
        )
        storage_dir = get_kb_storage_dir(kb.id)
        created_storage = not storage_dir.exists()
        storage_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._db.create_knowledge_base(kb)
        except Exception:
            # File-system creation precedes publication to avoid a DB row
            # pointing to a missing directory. Undo only the directory this
            # operation created; never remove a pre-existing user directory.
            if created_storage:
                shutil.rmtree(storage_dir)
            raise
        logger.info("Created knowledge base '%s' (id=%s)", name, kb.id)
        return kb

    def update(self, kb_id: str, **kwargs: Any) -> KnowledgeBase | None:
        previous = self._db.get_knowledge_base(kb_id)
        self._db.update_knowledge_base(kb_id, **kwargs)
        updated = self._db.get_knowledge_base(kb_id)
        if previous and updated and self._index_inputs_changed(previous, updated):
            self.mark_indexes_stale([kb_id])
        return updated

    async def delete(self, kb_id: str) -> bool:
        """Delete a KB after cancelling work; retain failed vector cleanup durably."""
        kb = self._db.get_knowledge_base(kb_id)
        if not kb:
            return False

        await self._coordinator.cancel_and_wait(kb_id)
        async with self._coordinator.job(kb_id, "delete_knowledge_base"):
            storage_dir = get_kb_storage_dir(kb_id)
            if await asyncio.to_thread(storage_dir.exists):
                try:
                    await asyncio.to_thread(shutil.rmtree, storage_dir)
                except OSError as exc:
                    logger.exception("Failed to delete KB storage for %s", kb_id)
                    raise RuntimeError(
                        f"Knowledge-base files could not be deleted: {exc}"
                    ) from exc

            if self._index_manager:
                versions = {chunk.index_version for chunk in self._db.get_kb_chunks_by_kb(kb_id)}
                if kb.active_index_version:
                    versions.add(kb.active_index_version)
                for version in versions:
                    await self._index_manager.delete_index_or_enqueue(
                        kb_id,
                        version,
                        "delete_knowledge_base",
                        (
                            kb.active_vector_table_name
                            if version == kb.active_index_version
                            else ""
                        ),
                        (
                            kb.active_vector_backend_fingerprint
                            if version == kb.active_index_version
                            else ""
                        ),
                    )

            self._db.delete_knowledge_base(kb_id)
            self.mark_index_rebuilt(kb_id)

        logger.info("Deleted knowledge base '%s' (id=%s)", kb.name, kb_id)
        return True

    # ── Statistics ────────────────────────────────────────────────────

    def update_statistics(self, kb_id: str) -> None:
        """Recompute document_count and chunk_count from related rows."""
        kb = self._db.get_knowledge_base(kb_id)
        if kb is None:
            return
        chunks = self._db.get_kb_chunks_by_index(kb_id, kb.active_index_version)
        doc_count = len({chunk.document_id for chunk in chunks})
        chunk_count = len(chunks)
        self._db.update_knowledge_base(
            kb_id,
            document_count=doc_count,
            chunk_count=chunk_count,
        )

    # ── Model availability ─────────────────────────────────────────────

    def check_model_availability(self, kb_id: str) -> dict[str, bool]:
        """Check whether the embedding/reranker models are still available.

        Returns dict with keys 'embedding_available' and 'reranker_available'.
        """
        kb = self._db.get_knowledge_base(kb_id)
        if not kb:
            return {"embedding_available": False, "reranker_available": False}

        embedding_available = False
        reranker_available = True  # no reranker => considered available

        if kb.embedding_model_id and kb.embedding_router_config_id:
            config = self._db.get_router_config(kb.embedding_router_config_id)
            if config and config.base_url.strip() and config.api_key.strip():
                models = self._db.get_router_models(kb.embedding_router_config_id)
                embedding_available = any(
                    m.model_id == kb.embedding_model_id and m.is_selected for m in models
                )

        if kb.reranker_model_id and kb.reranker_router_config_id:
            config = self._db.get_router_config(kb.reranker_router_config_id)
            if config and config.base_url.strip() and config.api_key.strip():
                models = self._db.get_router_models(kb.reranker_router_config_id)
                reranker_available = any(
                    m.model_id == kb.reranker_model_id and m.is_selected for m in models
                )
            else:
                reranker_available = False

        return {
            "embedding_available": embedding_available,
            "reranker_available": reranker_available,
        }

    # ── Rebuild embeddings ─────────────────────────────────────────────

    async def rebuild_embeddings(
        self,
        kb_id: str,
        embedding_config: Any,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        """Re-embed all documents after an embedding model change."""
        if not self._orchestrator or not self._index_manager:
            return {"success_count": 0, "error_count": 0, "errors": ["No orchestrator"]}

        kb = self._db.get_knowledge_base(kb_id)
        if not kb:
            return {"success_count": 0, "error_count": 0, "errors": ["KB not found"]}

        docs = self._db.get_kb_documents_by_kb(kb_id)
        try:
            async with self._coordinator.job(kb_id, "rebuild"):
                await self._index_manager.build_and_activate(
                    kb, docs, embedding_config, on_progress,
                )
        except Exception as exc:
            logger.exception("Rebuild failed for KB %s", kb_id)
            # Keep the old active version and its reconciled statistics intact.
            self.update_statistics(kb_id)
            return {"success_count": 0, "error_count": 1, "errors": [str(exc)]}

        self.mark_index_rebuilt(kb_id)
        return {"success_count": len(docs), "error_count": 0, "errors": []}

    # ----- Vector backend rebuild state -----

    def mark_all_indexes_stale(self) -> None:
        """Persist the KB IDs whose vectors must be rebuilt on the new backend."""
        pending_ids = [
            kb.id
            for kb in self._db.get_all_knowledge_bases()
            if self._db.get_kb_documents_by_kb(kb.id)
        ]
        self.mark_indexes_stale(pending_ids)

    def mark_indexes_stale(self, kb_ids: list[str]) -> None:
        """Add KBs with source documents to the persistent rebuild queue."""
        pending_ids = self._load_pending_kb_ids()
        for kb_id in kb_ids:
            if self._db.get_kb_documents_by_kb(kb_id):
                pending_ids.add(kb_id)
        self._save_pending_kb_ids(sorted(pending_ids))

    def is_index_stale(self, kb_id: str) -> bool:
        """Return whether a KB needs rebuilding before it may serve chat."""
        if kb_id in self._load_pending_kb_ids():
            return True
        kb = self._db.get_knowledge_base(kb_id)
        # Legacy indexes created before fingerprints remain usable until a
        # content-affecting setting changes, at which point ``update`` queues
        # an explicit rebuild.
        return bool(
            kb
            and kb.active_index_fingerprint
            and kb.active_index_fingerprint != build_index_fingerprint(kb)
        )

    def mark_index_rebuilt(self, kb_id: str) -> None:
        """Clear a KB from the persistent backend-switch rebuild queue."""
        pending_ids = self._load_pending_kb_ids()
        if kb_id in pending_ids:
            pending_ids.remove(kb_id)
            self._save_pending_kb_ids(sorted(pending_ids))

    def _load_pending_kb_ids(self) -> set[str]:
        raw = self._db.get_setting(SettingKeys.VECTOR_BACKEND_PENDING_KBS)
        if not raw:
            return set()
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid vector backend pending KB setting")
            return set()
        if not isinstance(value, list):
            return set()
        return {str(item) for item in value if item}

    def _save_pending_kb_ids(self, kb_ids: list[str]) -> None:
        self._db.set_setting(
            SettingKeys.VECTOR_BACKEND_PENDING_KBS,
            json.dumps(kb_ids),
        )

    @staticmethod
    def _index_inputs_changed(before: KnowledgeBase, after: KnowledgeBase) -> bool:
        """Return whether an edit invalidated the active index contents."""
        return build_index_fingerprint(before) != build_index_fingerprint(after)

    async def retry_pending_cleanup(self) -> int:
        """Retry failed remote/local vector cleanup recorded in the outbox."""
        if not self._index_manager:
            return 0
        return await self._index_manager.retry_pending_cleanup()

    def get_orphaned_vector_resources(self) -> list[dict[str, str]]:
        """List cleanup jobs that need their original backend to be selected.

        This is intentionally read-only: automated retries never send a
        delete operation to a backend other than the one recorded at index
        creation time.
        """
        current = self._db.get_setting(SettingKeys.VECTOR_BACKEND_FINGERPRINT) or "local-default"
        return [
            {
                "job_id": job.id,
                "knowledge_base_id": job.knowledge_base_id,
                "table_name": job.vector_table_name,
                "required_backend_fingerprint": job.backend_fingerprint,
            }
            for job in self._db.get_pending_kb_cleanup_jobs()
            if job.backend_fingerprint != current
        ]

    # ── Chat selection ────────────────────────────────────────────────

    def get_kb_for_chat_selection(self) -> list[dict[str, Any]]:
        """Return knowledge bases suitable for chat RAG selection.

        Only includes KBs that are ``active`` and have at least one
        embedded chunk.
        """
        all_kbs = self._db.get_all_knowledge_bases()
        result: list[dict[str, Any]] = []
        for kb in all_kbs:
            if kb.status != "active":
                continue
            if self.is_index_stale(kb.id):
                continue
            chunks = self._db.get_kb_chunks_by_index(kb.id, kb.active_index_version)
            if not chunks:
                continue
            result.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "document_count": len({chunk.document_id for chunk in chunks}),
                "chunk_count": len(chunks),
            })
        return result
