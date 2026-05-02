"""Document upload, management, and reprocessing service."""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from misaka.config import get_kb_storage_dir
from misaka.db.models import KBChunk, KBDocument
from misaka.services.knowledge.rag.abstractions import EmbeddingConfig

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.services.knowledge.rag_orchestrator import RAGOrchestrator

logger = logging.getLogger(__name__)

_BUF_SIZE = 65536
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".pdf": "pdf",
}


class DocumentService:
    """Upload, query, delete, and reprocess knowledge-base documents."""

    def __init__(
        self,
        db: DatabaseBackend,
        orchestrator: RAGOrchestrator,
    ) -> None:
        self._db = db
        self._orchestrator = orchestrator

    # ── Upload ────────────────────────────────────────────────────────

    async def upload_document(
        self,
        kb_id: str,
        file_path: str,
        embedding_config: EmbeddingConfig,
        on_progress: Callable[[str], None] | None = None,
    ) -> KBDocument:
        """Upload a single file: validate → hash → dedup → ingest → persist."""
        src = Path(file_path)
        file_type = self._resolve_file_type(src)

        file_size = src.stat().st_size
        if file_size > MAX_FILE_SIZE:
            raise ValueError(
                f"File too large ({file_size / (1024*1024):.1f} MB). "
                f"Maximum allowed size is {MAX_FILE_SIZE / (1024*1024):.0f} MB."
            )

        file_hash = self._compute_hash(src)

        dup = self._db.get_kb_document_by_hash(kb_id, file_hash)
        if dup:
            raise DuplicateDocumentError(
                f"Document '{src.name}' already exists in this knowledge base "
                f"(id={dup.id})."
            )

        kb = self._db.get_knowledge_base(kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        doc_id = str(uuid.uuid4())
        storage_dir = get_kb_storage_dir(kb_id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        dest = storage_dir / f"{doc_id}_{src.name}"
        shutil.copy2(str(src), str(dest))

        doc = KBDocument(
            id=doc_id,
            knowledge_base_id=kb_id,
            file_name=src.name,
            file_type=file_type,
            file_size=src.stat().st_size,
            file_hash=file_hash,
            storage_path=str(dest),
            status="parsing",
        )
        self._db.create_kb_document(doc)

        try:
            result = await self._orchestrator.ingest_document(
                file_path=str(dest),
                file_type=file_type,
                kb=kb,
                embedding_config=embedding_config,
                on_progress=on_progress,
            )

            if result.error:
                self._db.update_kb_document(doc_id, status="error", error_message=result.error)
                doc.status = "error"
                doc.error_message = result.error
                return doc

            self._persist_chunks(doc_id, kb_id, result.chunks)
            self._db.update_kb_document(
                doc_id,
                content_text=result.content_text,
                content_length=result.content_length,
                chunk_count=result.chunk_count,
                status="ready",
            )
            if result.dimensions and kb.embedding_dimensions == 0:
                self._db.update_knowledge_base(
                    kb_id, embedding_dimensions=result.dimensions,
                )

            doc.status = "ready"
            doc.content_text = result.content_text
            doc.content_length = result.content_length
            doc.chunk_count = result.chunk_count

        except Exception as exc:
            logger.exception("Failed to process document %s", src.name)
            self._db.update_kb_document(doc_id, status="error", error_message=str(exc))
            doc.status = "error"
            doc.error_message = str(exc)

        return doc

    async def upload_documents_batch(
        self,
        kb_id: str,
        file_paths: list[str],
        embedding_config: EmbeddingConfig,
        on_progress: Callable[[str, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Upload multiple files, returning a summary per file."""
        summaries: list[dict[str, Any]] = []
        for path in file_paths:
            file_name = Path(path).name

            def _progress(stage: str, _fn: str = file_name) -> None:
                if on_progress:
                    on_progress(_fn, stage)

            try:
                doc = await self.upload_document(
                    kb_id, path, embedding_config, on_progress=_progress,
                )
                summaries.append({
                    "file_name": file_name,
                    "status": doc.status,
                    "doc_id": doc.id,
                    "error": doc.error_message or None,
                })
            except DuplicateDocumentError:
                summaries.append({
                    "file_name": file_name,
                    "status": "duplicate",
                    "doc_id": None,
                    "error": "Duplicate file",
                })
            except Exception as exc:
                summaries.append({
                    "file_name": file_name,
                    "status": "error",
                    "doc_id": None,
                    "error": str(exc),
                })
        return summaries

    # ── Queries ───────────────────────────────────────────────────────

    def get_documents(self, kb_id: str) -> list[KBDocument]:
        return self._db.get_kb_documents_by_kb(kb_id)

    def get_document(self, doc_id: str) -> KBDocument | None:
        return self._db.get_kb_document(doc_id)

    def get_document_content(self, doc_id: str) -> str:
        """Return the parsed plain-text content stored in the DB."""
        doc = self._db.get_kb_document(doc_id)
        return doc.content_text if doc else ""

    # ── Delete ────────────────────────────────────────────────────────

    def delete_document(self, doc_id: str) -> bool:
        doc = self._db.get_kb_document(doc_id)
        if not doc:
            return False

        chunks = self._db.get_kb_chunks_by_document(doc_id)
        chunk_ids = [c.id for c in chunks]
        if chunk_ids:
            try:
                self._orchestrator.delete_chunks_from_vector_store(
                    doc.knowledge_base_id, chunk_ids,
                )
            except Exception:
                logger.exception("Failed to remove vectors for doc %s", doc_id)

        self._db.delete_kb_document(doc_id)

        if doc.storage_path:
            p = Path(doc.storage_path)
            if p.exists():
                p.unlink(missing_ok=True)

        logger.info("Deleted document '%s' (id=%s)", doc.file_name, doc_id)
        return True

    # ── Reprocess ─────────────────────────────────────────────────────

    async def reprocess_document(
        self,
        doc_id: str,
        embedding_config: EmbeddingConfig,
        on_progress: Callable[[str], None] | None = None,
    ) -> KBDocument | None:
        """Re-parse and re-embed an existing document."""
        doc = self._db.get_kb_document(doc_id)
        if not doc or not doc.storage_path:
            return None

        kb = self._db.get_knowledge_base(doc.knowledge_base_id)
        if not kb:
            return None

        old_chunks = self._db.get_kb_chunks_by_document(doc_id)
        old_ids = [c.id for c in old_chunks]
        if old_ids:
            try:
                self._orchestrator.delete_chunks_from_vector_store(
                    doc.knowledge_base_id, old_ids,
                )
            except Exception:
                logger.exception("Failed to remove old vectors for doc %s", doc_id)
        self._db.delete_kb_chunks_by_document(doc_id)

        self._db.update_kb_document(doc_id, status="parsing", error_message="")

        result = await self._orchestrator.ingest_document(
            file_path=doc.storage_path,
            file_type=doc.file_type,
            kb=kb,
            embedding_config=embedding_config,
            on_progress=on_progress,
        )

        if result.error:
            self._db.update_kb_document(
                doc_id, status="error", error_message=result.error,
            )
        else:
            self._persist_chunks(doc_id, doc.knowledge_base_id, result.chunks)
            self._db.update_kb_document(
                doc_id,
                content_text=result.content_text,
                content_length=result.content_length,
                chunk_count=result.chunk_count,
                status="ready",
            )

        return self._db.get_kb_document(doc_id)

    # ── Dedup helper ──────────────────────────────────────────────────

    def check_duplicate(self, kb_id: str, file_path: str) -> KBDocument | None:
        """Return the existing document if a file with the same hash exists."""
        file_hash = self._compute_hash(Path(file_path))
        return self._db.get_kb_document_by_hash(kb_id, file_hash)

    # ── Private helpers ───────────────────────────────────────────────

    def _persist_chunks(
        self,
        doc_id: str,
        kb_id: str,
        chunks: list,
    ) -> None:
        """Write ChunkData objects to the kb_chunks table.

        The chunk ID is derived from the same logic used by the vector
        store, so that ``delete_document`` can reliably remove vectors by
        ID later.
        """
        db_chunks: list[KBChunk] = []
        for c in chunks:
            cid = str(c.metadata.get("chunk_db_id", f"chunk_{c.index}"))
            db_chunks.append(KBChunk(
                id=cid,
                document_id=doc_id,
                knowledge_base_id=kb_id,
                content=c.content,
                chunk_index=c.index,
                start_char=c.start_char,
                end_char=c.end_char,
                metadata_json=self._safe_json(c.metadata),
                is_embedded=1,
            ))
        if db_chunks:
            self._db.create_kb_chunks_batch(db_chunks)
            self._db.update_kb_chunk_embedded([c.id for c in db_chunks])

    @staticmethod
    def _resolve_file_type(path: Path) -> str:
        ext = path.suffix.lower()
        file_type = SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        return file_type

    @staticmethod
    def _compute_hash(path: Path) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                data = f.read(_BUF_SIZE)
                if not data:
                    break
                sha.update(data)
        return sha.hexdigest()

    @staticmethod
    def _safe_json(data: dict) -> str:
        import json
        try:
            return json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            return "{}"


class DuplicateDocumentError(Exception):
    """Raised when attempting to upload a document that already exists."""
