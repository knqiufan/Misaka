"""Document upload, management, and reprocessing service."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from misaka.config import get_kb_storage_dir
from misaka.db.models import KBDocument
from misaka.services.knowledge.index_manager import KBIndexManager
from misaka.services.knowledge.job_coordinator import KnowledgeBaseJobCoordinator
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
        coordinator: KnowledgeBaseJobCoordinator | None = None,
    ) -> None:
        self._db = db
        self._orchestrator = orchestrator
        self._index_manager = KBIndexManager(db, orchestrator)
        self._coordinator = coordinator or KnowledgeBaseJobCoordinator(db)

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
            async with self._coordinator.job(kb_id, "upload", doc_id):
                self._db.update_kb_document(doc_id, status="parsing", error_message="")
                current_docs = self._documents_for_next_index(kb_id, {doc_id})
                await self._index_manager.build_and_activate(
                    kb, current_docs, embedding_config, on_progress,
                )
                updated = self._db.get_kb_document(doc_id)
                if updated is not None:
                    return updated
        except asyncio.CancelledError:
            logger.warning("Upload cancelled for document %s", src.name)
            self._db.update_kb_document(doc_id, status="error", error_message="Upload cancelled")
            doc.status = "error"
            raise
        except Exception as exc:
            logger.exception("Failed to process document %s", src.name)
            self._db.update_kb_document(doc_id, status="error", error_message=str(exc))
            doc.status = "error"
            doc.error_message = str(exc)

        return self._db.get_kb_document(doc_id) or doc

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

    async def delete_document(
        self, doc_id: str, embedding_config: EmbeddingConfig,
    ) -> bool:
        """Cancel in-flight work, publish an index without this document, then delete it."""
        doc = self._db.get_kb_document(doc_id)
        if not doc:
            return False

        await self._coordinator.cancel_and_wait(doc.knowledge_base_id)
        async with self._coordinator.job(doc.knowledge_base_id, "delete_document", doc_id):
            kb = self._db.get_knowledge_base(doc.knowledge_base_id)
            if kb is None:
                return False
            remaining_docs = [
                item for item in self._documents_for_next_index(doc.knowledge_base_id, set())
                if item.id != doc_id
            ]
            await self._index_manager.build_and_activate(
                kb, remaining_docs, embedding_config,
            )
            self._db.delete_kb_document(doc_id)

            if doc.storage_path:
                path = Path(doc.storage_path)
                if path.exists():
                    path.unlink(missing_ok=True)

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

        try:
            async with self._coordinator.job(doc.knowledge_base_id, "reprocess", doc_id):
                # This only signals UI activity; the active chunk rows and
                # document statistics remain untouched until activation.
                self._db.update_kb_document(doc_id, status="embedding", error_message="")
                current_docs = self._documents_for_next_index(
                    doc.knowledge_base_id, {doc_id},
                )
                await self._index_manager.build_and_activate(
                    kb, current_docs, embedding_config, on_progress,
                )
        except asyncio.CancelledError:
            self._db.update_kb_document(
                doc_id, status=doc.status, error_message=doc.error_message,
            )
            raise
        except Exception:
            # Reprocessing an existing document must not make its known-good
            # active version appear failed or unavailable.
            self._db.update_kb_document(
                doc_id, status=doc.status, error_message=doc.error_message,
            )
            raise
        return self._db.get_kb_document(doc_id)

    # ── Dedup helper ──────────────────────────────────────────────────

    def check_duplicate(self, kb_id: str, file_path: str) -> KBDocument | None:
        """Return the existing document if a file with the same hash exists."""
        file_hash = self._compute_hash(Path(file_path))
        return self._db.get_kb_document_by_hash(kb_id, file_hash)

    # ── Private helpers ───────────────────────────────────────────────

    def _documents_for_next_index(
        self, kb_id: str, include_ids: set[str],
    ) -> list[KBDocument]:
        """Return documents represented by the next complete index snapshot."""
        return [
            doc
            for doc in self._db.get_kb_documents_by_kb(kb_id)
            if doc.status == "ready" or doc.id in include_ids
        ]


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

class DuplicateDocumentError(Exception):
    """Raised when attempting to upload a document that already exists."""
