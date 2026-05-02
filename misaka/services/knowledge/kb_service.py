"""Knowledge base lifecycle management service."""

from __future__ import annotations

import logging
import shutil
import uuid
from typing import TYPE_CHECKING, Any

from misaka.config import get_kb_storage_dir
from misaka.db.models import KnowledgeBase

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
    ) -> None:
        self._db = db
        self._orchestrator = orchestrator

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
        self._db.create_knowledge_base(kb)
        storage_dir = get_kb_storage_dir(kb.id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created knowledge base '%s' (id=%s)", name, kb.id)
        return kb

    def update(self, kb_id: str, **kwargs: Any) -> KnowledgeBase | None:
        self._db.update_knowledge_base(kb_id, **kwargs)
        return self._db.get_knowledge_base(kb_id)

    def delete(self, kb_id: str) -> bool:
        kb = self._db.get_knowledge_base(kb_id)
        if not kb:
            return False

        if self._orchestrator:
            try:
                self._orchestrator.drop_kb_vectors(kb_id)
            except Exception:
                logger.exception("Failed to drop vectors for kb %s", kb_id)

        self._db.delete_knowledge_base(kb_id)

        storage_dir = get_kb_storage_dir(kb_id)
        if storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)

        logger.info("Deleted knowledge base '%s' (id=%s)", kb.name, kb_id)
        return True

    # ── Statistics ────────────────────────────────────────────────────

    def update_statistics(self, kb_id: str) -> None:
        """Recompute document_count and chunk_count from related rows."""
        docs = self._db.get_kb_documents_by_kb(kb_id)
        doc_count = len(docs)
        chunk_count = sum(d.chunk_count for d in docs)
        self._db.update_knowledge_base(
            kb_id,
            document_count=doc_count,
            chunk_count=chunk_count,
        )

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
            if kb.chunk_count <= 0:
                continue
            result.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "document_count": kb.document_count,
                "chunk_count": kb.chunk_count,
            })
        return result
