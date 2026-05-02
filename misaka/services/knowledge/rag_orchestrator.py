"""RAG pipeline orchestrator — business-layer entry point.

Depends **only** on the ABC interfaces defined in ``rag.abstractions``,
never on LangChain or any other framework directly.  The concrete adapter
instances are injected via :class:`RAGComponentFactory`.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Callable

from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    EmbeddingConfig,
    IngestResult,
    RerankerConfig,
    RetrievalResult,
)
from misaka.services.knowledge.rag.factory import RAGComponentFactory

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import KBSearchResult, KnowledgeBase

logger = logging.getLogger(__name__)


class RAGOrchestrator:
    """Orchestrate the full RAG pipeline (ingest + retrieve).

    All heavy lifting is delegated to the six abstract components created
    by the factory.  This class is responsible for *sequencing* and
    *coordinating* them.
    """

    def __init__(
        self,
        factory: RAGComponentFactory,
        db: DatabaseBackend,
    ) -> None:
        self._db = db
        self._factory = factory
        self._parser = None
        self._chunker = None
        self._embedding = None
        self._vector_store = None
        self._retriever = None
        self._reranker = None

    def _ensure_components(self) -> None:
        """Lazily create all RAG components on first use."""
        if self._parser is not None:
            return
        self._parser = self._factory.create_parser()
        self._chunker = self._factory.create_chunker()
        self._embedding = self._factory.create_embedding_provider()
        self._vector_store = self._factory.create_vector_store()
        self._retriever = self._factory.create_retriever(self._vector_store)
        self._reranker = self._factory.create_reranker()

    # ── Ingest ────────────────────────────────────────────────────────

    async def ingest_document(
        self,
        file_path: str,
        file_type: str,
        kb: KnowledgeBase,
        embedding_config: EmbeddingConfig,
        on_progress: Callable[[str], None] | None = None,
    ) -> IngestResult:
        """Full ingestion pipeline: parse → chunk → embed → store.

        Args:
            file_path: Absolute path to the source file.
            file_type: File type identifier (txt/markdown/docx/xlsx/pdf).
            kb: The target knowledge base (carries chunking config).
            embedding_config: Embedding API connection info.
            on_progress: Optional callback receiving status messages.

        Returns:
            An :class:`IngestResult` summarising the operation.  Each
            chunk in ``IngestResult.chunks`` has a globally unique
            ``chunk_db_id`` in its metadata, matching the ID used in
            the vector store.
        """
        self._ensure_components()
        try:
            _notify(on_progress, "parsing")
            parsed = await self._parser.parse(file_path, file_type)
            if not parsed.text.strip():
                return IngestResult(
                    content_text="",
                    content_length=0,
                    chunk_count=0,
                    chunks=[],
                    dimensions=0,
                )

            _notify(on_progress, "chunking")
            chunks = self._chunker.chunk(
                parsed.text,
                file_type,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
                metadata=parsed.metadata,
            )
            if not chunks:
                return IngestResult(
                    content_text=parsed.text,
                    content_length=len(parsed.text),
                    chunk_count=0,
                    chunks=[],
                    dimensions=0,
                )

            for c in chunks:
                c.metadata["chunk_db_id"] = str(uuid.uuid4())

            _notify(on_progress, "embedding")
            texts = [c.content for c in chunks]
            embeddings = await self._embedding.embed_texts(texts, embedding_config)

            dimensions = self._embedding.get_dimensions(embeddings[0])
            table_name = self._get_table_name(kb.id)

            _notify(on_progress, "storing")
            self._vector_store.ensure_table(table_name, dimensions)
            self._vector_store.add_chunks(table_name, chunks, embeddings)

            return IngestResult(
                content_text=parsed.text,
                content_length=len(parsed.text),
                chunk_count=len(chunks),
                chunks=chunks,
                dimensions=dimensions,
            )

        except Exception as exc:
            logger.exception("Ingest failed for %s", file_path)
            return IngestResult(
                content_text="",
                content_length=0,
                chunk_count=0,
                chunks=[],
                dimensions=0,
                error=str(exc),
            )

    # ── Retrieve ──────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        embedding_configs: dict[str, EmbeddingConfig],
        reranker_config: RerankerConfig | None = None,
        top_k: int = 5,
    ) -> list[KBSearchResult]:
        """Retrieve across multiple knowledge bases, optionally reranking.

        Args:
            query: User query text.
            kb_ids: IDs of knowledge bases to search.
            embedding_configs: ``{kb_id: EmbeddingConfig}`` mapping.
            reranker_config: If provided, results are reranked.
            top_k: Final number of results to return.
        """
        self._ensure_components()
        all_results: list[RetrievalResult] = []

        for kb_id in kb_ids:
            config = embedding_configs.get(kb_id)
            if config is None:
                logger.warning("No embedding config for kb %s, skipping", kb_id)
                continue
            table_name = self._get_table_name(kb_id)
            query_vec = await self._embedding.embed_query(query, config)

            results = await self._retriever.retrieve(
                query=query,
                query_embedding=query_vec,
                table_name=table_name,
                top_k=top_k * 2,
            )
            for r in results:
                r.metadata["_kb_id"] = kb_id
            all_results.extend(results)

        if reranker_config and reranker_config.model_id:
            all_results = await self._reranker.rerank(
                query, all_results, reranker_config,
            )

        return self._to_search_results(all_results[:top_k])

    def format_context(self, results: list[KBSearchResult]) -> str:
        """Format retrieval results as a text block for prompt injection."""
        if not results:
            return ""

        lines: list[str] = []
        for r in results:
            header = f"[来源: {r.document_name} | 片段 {r.chunk_index + 1}]"
            lines.append(header)
            lines.append(r.content)
            lines.append("")

        body = "\n".join(lines).strip()
        return (
            "---\n"
            "以下是从知识库中检索到的相关参考资料，"
            "请结合这些资料回答上述问题：\n\n"
            f"<reference_materials>\n{body}\n</reference_materials>"
        )

    # ── Resource management ───────────────────────────────────────────

    def drop_kb_vectors(self, kb_id: str) -> None:
        """Delete the vector table for a knowledge base."""
        self._ensure_components()
        self._vector_store.drop_table(self._get_table_name(kb_id))

    def delete_chunks_from_vector_store(
        self,
        kb_id: str,
        chunk_ids: list[str],
    ) -> None:
        """Remove specific chunk vectors from the store."""
        if chunk_ids:
            self._ensure_components()
            self._vector_store.delete_by_ids(
                self._get_table_name(kb_id), chunk_ids,
            )

    def close(self) -> None:
        """Release all underlying resources."""
        if self._vector_store is not None:
            self._vector_store.close()

    # ── Private helpers ───────────────────────────────────────────────

    @staticmethod
    def _get_table_name(kb_id: str) -> str:
        return f"kb_vec_{kb_id.replace('-', '')[:8]}"

    def _to_search_results(
        self,
        results: list[RetrievalResult],
    ) -> list[KBSearchResult]:
        """Enrich ``RetrievalResult`` with business info from the DB."""
        from misaka.db.models import KBSearchResult as KBSResult

        enriched: list[KBSResult] = []
        kb_cache: dict[str, str] = {}
        doc_cache: dict[str, tuple[str, str]] = {}

        for r in results:
            kb_id = r.metadata.get("_kb_id", "")
            doc_id = r.metadata.get("document_id", "")

            kb_name = self._resolve_kb_name(kb_id, kb_cache)
            doc_name = self._resolve_doc_name(doc_id, doc_cache)

            enriched.append(KBSResult(
                chunk_id=r.chunk_id,
                document_id=doc_id,
                knowledge_base_id=kb_id,
                knowledge_base_name=kb_name,
                document_name=doc_name,
                content=r.content,
                score=r.score,
                chunk_index=r.metadata.get("chunk_index", 0),
                metadata={
                    k: v for k, v in r.metadata.items()
                    if not k.startswith("_")
                },
            ))
        return enriched

    def _resolve_kb_name(
        self, kb_id: str, cache: dict[str, str],
    ) -> str:
        if not kb_id:
            return ""
        if kb_id not in cache:
            kb = self._db.get_knowledge_base(kb_id)
            cache[kb_id] = kb.name if kb else ""
        return cache[kb_id]

    def _resolve_doc_name(
        self, doc_id: str, cache: dict[str, tuple[str, str]],
    ) -> str:
        if not doc_id:
            return ""
        if doc_id not in cache:
            doc = self._db.get_kb_document(doc_id)
            cache[doc_id] = (doc.file_name, doc.knowledge_base_id) if doc else ("", "")
        return cache[doc_id][0]


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is not None:
        callback(stage)
