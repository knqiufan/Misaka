"""RAG pipeline orchestrator — business-layer entry point.

Depends **only** on the ABC interfaces defined in ``rag.abstractions``,
never on LangChain or any other framework directly.  The concrete adapter
instances are injected via :class:`RAGComponentFactory`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    EmbeddingConfig,
    IngestResult,
    KBRetrievalConfig,
    RerankerConfig,
    RetrievalResult,
)
from misaka.services.knowledge.rag.factory import RAGComponentFactory

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import KBSearchResult, KnowledgeBase

logger = logging.getLogger(__name__)

RETRIEVAL_DEADLINE_SECONDS = 10.0


@dataclass
class RAGRetrievalOutcome:
    """Observable outcome of a multi-KB retrieval request."""

    results: list[KBSearchResult] = field(default_factory=list)
    per_kb_errors: dict[str, str] = field(default_factory=dict)
    timed_out: bool = False


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
        document_id: str = "",
        index_version: str = "",
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
                    error="No extractable text content found in document",
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
                c.metadata["document_id"] = document_id
                c.metadata["chunk_index"] = c.index

            _notify(on_progress, "embedding")
            texts = [c.content for c in chunks]
            embeddings = await self._embedding.embed_texts(texts, embedding_config)

            dimensions = self._embedding.get_dimensions(embeddings[0])
            table_name = self._get_table_name(kb.id, index_version)

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

        except asyncio.CancelledError:
            logger.warning("Ingest cancelled for %s", file_path)
            raise
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
        kb_retrieval_configs: dict[str, KBRetrievalConfig] | None = None,
    ) -> list[KBSearchResult]:
        """Retrieve across multiple KBs and return only the final results.

        This compatibility wrapper intentionally hides diagnostics. Call
        :meth:`retrieve_with_diagnostics` when the caller needs to inform the
        user about partial failures or a global deadline.
        """
        outcome = await self.retrieve_with_diagnostics(
            query=query,
            kb_ids=kb_ids,
            embedding_configs=embedding_configs,
            reranker_config=reranker_config,
            top_k=top_k,
            kb_retrieval_configs=kb_retrieval_configs,
        )
        return outcome.results

    async def retrieve_with_diagnostics(
        self,
        query: str,
        kb_ids: list[str],
        embedding_configs: dict[str, EmbeddingConfig],
        reranker_config: RerankerConfig | None = None,
        top_k: int = 5,
        kb_retrieval_configs: dict[str, KBRetrievalConfig] | None = None,
    ) -> RAGRetrievalOutcome:
        """Retrieve with a ten-second global deadline and structured errors.

        Every KB supplies a candidate limit and threshold. Its candidates are
        optionally reranked by *that KB's* configured reranker, normalized to
        ``[0, 1]``, filtered by its threshold, and only then merged into the
        session-level ``top_k``. This avoids one selected KB's reranker or
        score scale changing the semantics of another.

        ``reranker_config`` is retained for callers using the legacy API: it
        becomes the default per-KB reranker when no per-KB policy is supplied.
        New callers should use ``kb_retrieval_configs``.

        Args:
            query: User query text.
            kb_ids: IDs of knowledge bases to search.
            embedding_configs: ``{kb_id: EmbeddingConfig}`` mapping.
            reranker_config: Backwards-compatible default reranker.
            top_k: Session-level final number of results to return.
            kb_retrieval_configs: Per-KB candidate/reranker policies.
        """
        try:
            return await asyncio.wait_for(
                self._retrieve_with_diagnostics_impl(
                    query=query,
                    kb_ids=kb_ids,
                    embedding_configs=embedding_configs,
                    reranker_config=reranker_config,
                    top_k=top_k,
                    kb_retrieval_configs=kb_retrieval_configs or {},
                ),
                timeout=RETRIEVAL_DEADLINE_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("RAG retrieval exceeded %.1f seconds", RETRIEVAL_DEADLINE_SECONDS)
            return RAGRetrievalOutcome(timed_out=True)

    async def _retrieve_with_diagnostics_impl(
        self,
        *,
        query: str,
        kb_ids: list[str],
        embedding_configs: dict[str, EmbeddingConfig],
        reranker_config: RerankerConfig | None,
        top_k: int,
        kb_retrieval_configs: dict[str, KBRetrievalConfig],
    ) -> RAGRetrievalOutcome:
        self._ensure_components()
        all_results: list[RetrievalResult] = []
        per_kb_errors: dict[str, str] = {}

        groups = self._group_by_embedding_model(kb_ids, embedding_configs)
        configured_kb_ids = {kb_id for _, ids in groups for kb_id in ids}
        for kb_id in kb_ids:
            if kb_id not in configured_kb_ids:
                per_kb_errors[kb_id] = "No embedding configuration is available"

        for config, group_kb_ids in groups:
            try:
                query_vec = await self._embedding.embed_query(query, config)
            except Exception as exc:
                logger.warning(
                    "Embedding query failed for model %s: %s", config.model_id, exc,
                )
                message = f"Query embedding failed: {exc}"
                per_kb_errors.update({kb_id: message for kb_id in group_kb_ids})
                continue
            for kb_id in group_kb_ids:
                policy = kb_retrieval_configs.get(kb_id, KBRetrievalConfig())
                candidate_top_k = max(1, policy.top_k)
                try:
                    results = await self._retrieve_single_kb(
                        query, query_vec, kb_id, candidate_top_k,
                    )
                except Exception as exc:
                    logger.warning("Retrieval failed for kb %s: %s", kb_id, exc)
                    per_kb_errors[kb_id] = f"Retrieval failed: {exc}"
                    continue

                kb_reranker = policy.reranker_config or reranker_config
                if kb_reranker and kb_reranker.model_id and results:
                    try:
                        results = await self._reranker.rerank(query, results, kb_reranker)
                    except Exception as exc:
                        logger.warning("Reranker failed for kb %s: %s", kb_id, exc)
                        per_kb_errors[kb_id] = f"Reranker failed: {exc}"

                results = self._normalize_scores(results)
                all_results.extend(
                    result
                    for result in results
                    if result.score >= policy.similarity_threshold
                )

        all_results.sort(key=lambda r: (-r.score, r.chunk_id))
        return RAGRetrievalOutcome(
            results=self._to_search_results(all_results[:max(1, top_k)]),
            per_kb_errors=per_kb_errors,
        )

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

    def drop_kb_vectors(self, kb_id: str, index_version: str = "") -> None:
        """Delete a specific version of a knowledge-base vector table."""
        self._ensure_components()
        self._vector_store.drop_table(self._get_table_name(kb_id, index_version))

    def delete_chunks_from_vector_store(
        self,
        kb_id: str,
        chunk_ids: list[str],
        index_version: str = "",
    ) -> None:
        """Remove specific chunk vectors from the store."""
        if chunk_ids:
            self._ensure_components()
            self._vector_store.delete_by_ids(
                self._get_table_name(kb_id, index_version), chunk_ids,
            )

    def close(self) -> None:
        """Release all underlying resources."""
        if self._vector_store is not None:
            self._vector_store.close()

    # ── Private helpers ───────────────────────────────────────────────

    @staticmethod
    def _group_by_embedding_model(
        kb_ids: list[str],
        embedding_configs: dict[str, EmbeddingConfig],
    ) -> list[tuple[EmbeddingConfig, list[str]]]:
        """Group knowledge bases by their embedding model.

        Returns a list of ``(config, [kb_id, …])`` tuples so each
        distinct model only needs one ``embed_query`` call.
        """
        groups: dict[str, tuple[EmbeddingConfig, list[str]]] = {}
        for kb_id in kb_ids:
            config = embedding_configs.get(kb_id)
            if config is None:
                logger.warning("No embedding config for kb %s, skipping", kb_id)
                continue
            key = f"{config.base_url}|{config.model_id}"
            if key not in groups:
                groups[key] = (config, [])
            groups[key][1].append(kb_id)
        return list(groups.values())

    async def _retrieve_single_kb(
        self,
        query: str,
        query_vec: list[float],
        kb_id: str,
        top_k: int,
    ) -> list[RetrievalResult]:
        """Retrieve from a single knowledge base and tag results."""
        kb = self._db.get_knowledge_base(kb_id)
        if kb is None:
            return []
        index_version = kb.active_index_version
        table_name = self._get_table_name(kb_id, index_version)
        chunks_for_bm25 = []
        if getattr(self._retriever, "requires_bm25_chunks", False):
            for chunk in self._db.get_kb_chunks_by_index(kb_id, index_version):
                metadata = {}
                try:
                    value = json.loads(chunk.metadata_json)
                    if isinstance(value, dict):
                        metadata = value
                except (TypeError, ValueError):
                    pass
                metadata.setdefault("chunk_db_id", chunk.id)
                metadata.setdefault("document_id", chunk.document_id)
                metadata.setdefault("chunk_index", chunk.chunk_index)
                chunks_for_bm25.append(
                    ChunkData(
                        content=chunk.content,
                        index=chunk.chunk_index,
                        start_char=chunk.start_char,
                        end_char=chunk.end_char,
                        metadata=metadata,
                    )
                )
        results = await self._retriever.retrieve(
            query=query,
            query_embedding=query_vec,
            table_name=table_name,
            top_k=top_k,
            chunks_for_bm25=chunks_for_bm25 or None,
        )
        for r in results:
            r.metadata["_kb_id"] = kb_id
        return results

    @staticmethod
    def _normalize_scores(
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """Min-Max normalise scores per ``_kb_id`` group to [0, 1].

        When results come from knowledge bases using different embedding
        models, the raw distance / similarity scores live on different
        scales.  Normalising per group removes that bias before merging.
        """
        if not results:
            return results

        from collections import defaultdict

        groups: dict[str, list[RetrievalResult]] = defaultdict(list)
        for r in results:
            groups[r.metadata.get("_kb_id", "")].append(r)

        normalised: list[RetrievalResult] = []
        for group_results in groups.values():
            scores = [r.score for r in group_results]
            min_s, max_s = min(scores), max(scores)
            score_range = max_s - min_s
            for r in group_results:
                r.score = (r.score - min_s) / score_range if score_range > 0 else 1.0
                normalised.append(r)

        return normalised

    @staticmethod
    def _get_table_name(kb_id: str, index_version: str = "") -> str:
        """Return the stable legacy or immutable-version vector table name."""
        base = f"kb_vec_{kb_id.replace('-', '')[:8]}"
        if not index_version:
            return base
        suffix = "".join(char for char in index_version if char.isalnum())[:16]
        if not suffix:
            raise ValueError("Index version must contain at least one alphanumeric character")
        return f"{base}_{suffix}"

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
