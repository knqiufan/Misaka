"""Copy-on-write construction and cleanup of knowledge-base vector indexes."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from misaka.config import SettingKeys
from misaka.db.models import KBChunk
from misaka.services.knowledge.index_fingerprint import build_index_fingerprint

if TYPE_CHECKING:
    from collections.abc import Callable

    from misaka.db.database import DatabaseBackend
    from misaka.db.models import KBDocument, KnowledgeBase
    from misaka.services.knowledge.rag.abstractions import EmbeddingConfig
    from misaka.services.knowledge.rag_orchestrator import RAGOrchestrator


@dataclass
class IndexBuildResult:
    """The outcome of a successfully activated index build."""

    index_version: str
    document_count: int
    chunk_count: int
    dimensions: int


class KBIndexManager:
    """Build complete immutable index versions, then atomically activate them."""

    def __init__(self, db: DatabaseBackend, orchestrator: RAGOrchestrator) -> None:
        self._db = db
        self._orchestrator = orchestrator

    async def build_and_activate(
        self,
        kb: KnowledgeBase,
        documents: list[KBDocument],
        embedding_config: EmbeddingConfig,
        on_progress: Callable[[str], None] | None = None,
    ) -> IndexBuildResult:
        """Build a complete replacement index without touching the active one.

        The vector store receives an isolated versioned table/collection.  DB
        chunk rows and document statistics are published together only after
        every source document has been parsed, embedded and written.  Any
        error removes the staging version and leaves the active version intact.
        """
        await self._validate_sources(documents)
        new_version = uuid.uuid4().hex
        staged_chunks: list[KBChunk] = []
        document_updates: dict[str, dict[str, Any]] = {}
        dimensions = 0

        try:
            for document in documents:
                result = await self._orchestrator.ingest_document(
                    file_path=document.storage_path,
                    file_type=document.file_type,
                    kb=kb,
                    embedding_config=embedding_config,
                    on_progress=on_progress,
                    document_id=document.id,
                    index_version=new_version,
                )
                if result.error:
                    raise RuntimeError(f"{document.file_name}: {result.error}")
                if not result.chunks:
                    raise RuntimeError(f"{document.file_name}: no chunks were produced")
                if dimensions and result.dimensions != dimensions:
                    raise RuntimeError(
                        f"{document.file_name}: embedding dimensions changed within one index build"
                    )
                dimensions = result.dimensions or dimensions
                staged_chunks.extend(
                    self._to_db_chunks(document.id, kb.id, new_version, result.chunks)
                )
                document_updates[document.id] = {
                    "content_text": result.content_text,
                    "content_length": result.content_length,
                    "chunk_count": result.chunk_count,
                    "status": "ready",
                    "error_message": "",
                }

            if documents and not dimensions:
                raise RuntimeError("Embedding provider returned no vector dimensions")

            old_version = kb.active_index_version
            old_table_name = kb.active_vector_table_name or self._orchestrator._legacy_table_name(
                kb.id, old_version,
            )
            old_backend_fingerprint = kb.active_vector_backend_fingerprint
            new_table_name = self._orchestrator._get_table_name(kb.id, new_version)
            self._db.activate_kb_index(
                kb.id,
                new_version,
                staged_chunks,
                document_updates,
                dimensions or kb.embedding_dimensions,
                build_index_fingerprint(
                    kb,
                    embedding_dimensions=dimensions or kb.embedding_dimensions,
                ),
                new_table_name,
                self._current_backend_fingerprint(),
            )
        except BaseException as exc:
            await self._discard_staging(kb.id, new_version, str(exc))
            raise

        await self._retire_index(
            kb.id,
            old_version,
            old_table_name,
            old_backend_fingerprint,
            operation="retire_previous_index",
        )
        return IndexBuildResult(
            index_version=new_version,
            document_count=len(document_updates),
            chunk_count=len(staged_chunks),
            dimensions=dimensions or kb.embedding_dimensions,
        )

    async def retry_pending_cleanup(self) -> int:
        """Retry every persisted vector-table deletion and return successes."""
        succeeded = 0
        for job in self._db.get_pending_kb_cleanup_jobs():
            if job.backend_fingerprint != self._current_backend_fingerprint():
                # Deleting a resource through a differently configured backend
                # could target an unrelated collection. Keep an explicit
                # outbox record for user/admin reconciliation instead.
                continue
            try:
                await self._orchestrator.drop_kb_vectors(
                    job.knowledge_base_id, job.index_version, job.vector_table_name,
                )
                self._db.delete_kb_chunks_by_index(
                    job.knowledge_base_id, job.index_version,
                )
                self._db.update_kb_cleanup_job(job.id, "completed")
                succeeded += 1
            except Exception as exc:
                self._db.update_kb_cleanup_job(job.id, "pending", str(exc))
        return succeeded

    async def delete_index_or_enqueue(
        self,
        kb_id: str,
        index_version: str,
        operation: str,
        vector_table_name: str = "",
        backend_fingerprint: str = "",
    ) -> bool:
        """Delete one index version, persisting retry work on failure."""
        current_fingerprint = self._current_backend_fingerprint()
        if backend_fingerprint != current_fingerprint:
            self._db.create_kb_cleanup_job(
                kb_id,
                index_version,
                operation,
                "Cleanup requires the backend that created this vector index.",
                vector_table_name,
                backend_fingerprint,
            )
            return False
        try:
            await self._orchestrator.drop_kb_vectors(
                kb_id, index_version, vector_table_name,
            )
        except Exception as exc:
            self._db.create_kb_cleanup_job(
                kb_id,
                index_version,
                operation,
                str(exc),
                vector_table_name,
                backend_fingerprint,
            )
            return False
        self._db.delete_kb_chunks_by_index(kb_id, index_version)
        return True

    async def _retire_index(
        self,
        kb_id: str,
        index_version: str,
        vector_table_name: str,
        backend_fingerprint: str,
        operation: str,
    ) -> None:
        # There is nothing to retire for a brand-new KB.  Retiring only when
        # DB rows exist avoids treating a missing legacy table as an error.
        if not self._db.get_kb_chunks_by_index(kb_id, index_version):
            return
        await self.delete_index_or_enqueue(
            kb_id,
            index_version,
            operation,
            vector_table_name,
            backend_fingerprint,
        )

    async def _discard_staging(
        self, kb_id: str, index_version: str, reason: str,
    ) -> None:
        try:
            await self._orchestrator.drop_kb_vectors(kb_id, index_version)
        except Exception as cleanup_error:
            self._db.create_kb_cleanup_job(
                kb_id,
                index_version,
                "discard_staged_index",
                f"build failed: {reason}; cleanup failed: {cleanup_error}",
                self._orchestrator._get_table_name(kb_id, index_version),
                self._current_backend_fingerprint(),
            )

    def _current_backend_fingerprint(self) -> str:
        """Return an explicit backend identity for cleanup safety checks."""
        return self._db.get_setting(SettingKeys.VECTOR_BACKEND_FINGERPRINT) or "local-default"

    @staticmethod
    async def _validate_sources(documents: list[KBDocument]) -> None:
        for document in documents:
            if not document.storage_path or not await asyncio.to_thread(
                Path(document.storage_path).is_file,
            ):
                raise FileNotFoundError(
                    f"Source file for '{document.file_name}' is missing; active index was preserved"
                )

    @staticmethod
    def _to_db_chunks(
        document_id: str,
        kb_id: str,
        index_version: str,
        chunks: list,
    ) -> list[KBChunk]:
        db_chunks: list[KBChunk] = []
        for chunk in chunks:
            metadata = "{}"
            with suppress(TypeError, ValueError):
                metadata = json.dumps(chunk.metadata, ensure_ascii=False)
            db_chunks.append(KBChunk(
                id=str(chunk.metadata["chunk_db_id"]),
                document_id=document_id,
                knowledge_base_id=kb_id,
                content=chunk.content,
                chunk_index=chunk.index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                metadata_json=metadata,
                is_embedded=1,
                index_version=index_version,
            ))
        return db_chunks
