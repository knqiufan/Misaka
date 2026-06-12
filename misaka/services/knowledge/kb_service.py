"""Knowledge base lifecycle management service."""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import uuid
from typing import TYPE_CHECKING, Any

from misaka.config import SettingKeys, get_kb_storage_dir
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
            if config:
                models = self._db.get_router_models(kb.embedding_router_config_id)
                embedding_available = any(
                    m.model_id == kb.embedding_model_id for m in models
                )

        if kb.reranker_model_id and kb.reranker_router_config_id:
            config = self._db.get_router_config(kb.reranker_router_config_id)
            if config:
                models = self._db.get_router_models(kb.reranker_router_config_id)
                reranker_available = any(
                    m.model_id == kb.reranker_model_id for m in models
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
        if not self._orchestrator:
            return {"success_count": 0, "error_count": 0, "errors": ["No orchestrator"]}

        kb = self._db.get_knowledge_base(kb_id)
        if not kb:
            return {"success_count": 0, "error_count": 0, "errors": ["KB not found"]}

        docs = self._db.get_kb_documents_by_kb(kb_id)
        success_count = 0
        error_count = 0
        errors: list[str] = []

        self._db.update_knowledge_base(kb_id, status="building")
        try:
            self._orchestrator.drop_kb_vectors(kb_id)
        except Exception:
            logger.info("No existing vector collection to drop for kb %s", kb_id)

        for doc in docs:
            try:
                await self._rebuild_single_doc(kb, doc, embedding_config, on_progress)
                success_count += 1
            except Exception as exc:
                logger.exception("Rebuild failed for doc %s", doc.id)
                error_count += 1
                errors.append(f"{doc.file_name}: {exc}")

        new_status = "active" if error_count == 0 else "error"
        self._db.update_knowledge_base(kb_id, status=new_status)
        self.update_statistics(kb_id)
        if error_count == 0:
            self.mark_index_rebuilt(kb_id)

        return {
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors,
        }

    # ----- Vector backend rebuild state -----

    def mark_all_indexes_stale(self) -> None:
        """Persist the KB IDs whose vectors must be rebuilt on the new backend."""
        pending_ids = [
            kb.id
            for kb in self._db.get_all_knowledge_bases()
            if self._db.get_kb_documents_by_kb(kb.id)
        ]
        self._save_pending_kb_ids(pending_ids)

    def is_index_stale(self, kb_id: str) -> bool:
        """Return whether a KB still needs an index rebuild after switching backend."""
        return kb_id in self._load_pending_kb_ids()

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

    async def _rebuild_single_doc(
        self,
        kb: KnowledgeBase,
        doc: Any,
        embedding_config: Any,
        on_progress: Any,
    ) -> None:
        """Delete old chunks/vectors and re-ingest a single document."""
        self._remove_old_chunks(doc)

        if not doc.storage_path:
            return

        result = await self._orchestrator.ingest_document(
            file_path=doc.storage_path,
            file_type=doc.file_type,
            kb=kb,
            embedding_config=embedding_config,
            on_progress=on_progress,
            document_id=doc.id,
        )
        if result.error:
            self._db.update_kb_document(doc.id, status="error", error_message=result.error)
            raise RuntimeError(result.error)

        self._persist_rebuilt_chunks(doc.id, doc.knowledge_base_id, result.chunks)
        self._db.update_kb_document(
            doc.id,
            content_text=result.content_text,
            content_length=result.content_length,
            chunk_count=result.chunk_count,
            status="ready",
        )
        if result.dimensions and kb.embedding_dimensions != result.dimensions:
            self._db.update_knowledge_base(
                kb.id, embedding_dimensions=result.dimensions,
            )

    def _remove_old_chunks(self, doc: Any) -> None:
        """Remove existing chunk rows and their vectors."""
        old_chunks = self._db.get_kb_chunks_by_document(doc.id)
        old_ids = [c.id for c in old_chunks]
        if old_ids:
            try:
                self._orchestrator.delete_chunks_from_vector_store(
                    doc.knowledge_base_id, old_ids,
                )
            except Exception:
                logger.warning("Failed to remove old vectors for doc %s", doc.id)
        self._db.delete_kb_chunks_by_document(doc.id)

    def _persist_rebuilt_chunks(
        self, doc_id: str, kb_id: str, chunks: list,
    ) -> None:
        """Write ChunkData objects to the kb_chunks table."""
        import json

        from misaka.db.models import KBChunk

        db_chunks: list[KBChunk] = []
        for c in chunks:
            cid = str(c.metadata.get("chunk_db_id", f"chunk_{c.index}"))
            meta = "{}"
            with contextlib.suppress(TypeError, ValueError):
                meta = json.dumps(c.metadata, ensure_ascii=False)
            db_chunks.append(KBChunk(
                id=cid,
                document_id=doc_id,
                knowledge_base_id=kb_id,
                content=c.content,
                chunk_index=c.index,
                start_char=c.start_char,
                end_char=c.end_char,
                metadata_json=meta,
                is_embedded=1,
            ))
        if db_chunks:
            self._db.create_kb_chunks_batch(db_chunks)
            self._db.update_kb_chunk_embedded([c.id for c in db_chunks])

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
