"""Hybrid retriever adapter (vector + BM25 with RRF fusion)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import defaultdict

from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    RetrievalResult,
    Retriever,
    VectorStore,
)

logger = logging.getLogger(__name__)

_DEFAULT_BM25_WEIGHT = 0.3
_DEFAULT_VEC_WEIGHT = 0.7
_RRF_K = 60  # RRF constant


class LCHybridRetriever(Retriever):
    """Retrieve chunks using vector search, optionally fused with BM25.

    When *chunks_for_bm25* is provided, both BM25 and vector results are
    combined using Reciprocal Rank Fusion (RRF).  Otherwise, only vector
    search is performed.
    """

    requires_bm25_chunks = True

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_weight: float = _DEFAULT_BM25_WEIGHT,
        vector_weight: float = _DEFAULT_VEC_WEIGHT,
    ) -> None:
        self._vector_store = vector_store
        self._bm25_weight = bm25_weight
        self._vector_weight = vector_weight

    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        table_name: str,
        top_k: int = 5,
        chunks_for_bm25: list[ChunkData] | None = None,
    ) -> list[RetrievalResult]:
        vec_results = await asyncio.to_thread(
            self._vector_store.search,
            table_name,
            query_embedding,
            top_k=top_k * 2,
        )

        if not chunks_for_bm25:
            return vec_results[:top_k]

        bm25_results = await asyncio.to_thread(
            self._bm25_search, query, chunks_for_bm25, top_k * 2,
        )
        return self._rrf_fusion(vec_results, bm25_results, top_k)

    # ------------------------------------------------------------------
    # BM25
    # ------------------------------------------------------------------

    @staticmethod
    def _bm25_search(
        query: str,
        chunks: list[ChunkData],
        top_k: int,
    ) -> list[RetrievalResult]:
        from rank_bm25 import BM25Okapi

        tokenized_corpus = [_tokenize(c.content) for c in chunks]
        tokenized_query = _tokenize(query)

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)

        scored = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        results: list[RetrievalResult] = []
        for idx, score in scored:
            if score <= 0:
                continue
            chunk = chunks[idx]
            results.append(RetrievalResult(
                chunk_id=_chunk_id(chunk),
                content=chunk.content,
                score=float(score),
                metadata=dict(chunk.metadata),
            ))
        return results

    # ------------------------------------------------------------------
    # Reciprocal Rank Fusion
    # ------------------------------------------------------------------

    def _rrf_fusion(
        self,
        vec_results: list[RetrievalResult],
        bm25_results: list[RetrievalResult],
        top_k: int,
    ) -> list[RetrievalResult]:
        scores: dict[str, float] = defaultdict(float)
        result_map: dict[str, RetrievalResult] = {}

        for rank, r in enumerate(_unique_results(vec_results)):
            scores[r.chunk_id] += self._vector_weight / (rank + _RRF_K)
            result_map[r.chunk_id] = r

        for rank, r in enumerate(_unique_results(bm25_results)):
            scores[r.chunk_id] += self._bm25_weight / (rank + _RRF_K)
            if r.chunk_id not in result_map:
                result_map[r.chunk_id] = r

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        fused: list[RetrievalResult] = []
        for chunk_id, fused_score in ranked:
            original = result_map[chunk_id]
            fused.append(RetrievalResult(
                chunk_id=original.chunk_id,
                content=original.content,
                score=fused_score,
                metadata=original.metadata,
            ))
        return fused


def _chunk_id(chunk: ChunkData) -> str:
    """Resolve the ID shared by BM25, the vector store, and persisted chunks."""
    value = str(chunk.metadata.get("chunk_db_id", "")).strip()
    if value:
        return value

    document_id = str(chunk.metadata.get("document_id", "")).strip() or "unknown-document"
    content_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()[:16]
    return f"{document_id}:chunk:{chunk.index}:{content_hash}"


def _unique_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Keep only the first result per real chunk ID, preserving rank order."""
    seen: set[str] = set()
    unique: list[RetrievalResult] = []
    for result in results:
        if result.chunk_id in seen:
            continue
        seen.add(result.chunk_id)
        unique.append(result)
    return unique


# ---------------------------------------------------------------------------
# Simple tokenizer (CJK-aware)
# ---------------------------------------------------------------------------

_CJK_RANGE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]"
)


def _tokenize(text: str) -> list[str]:
    """Whitespace + CJK character-level tokenizer.

    For CJK text we fall back to character unigrams which, while naive,
    works reasonably well with BM25 and avoids a heavy dependency on
    external segmenters like ``jieba``.
    """
    tokens: list[str] = []
    for word in text.lower().split():
        if _CJK_RANGE.search(word):
            tokens.extend(ch for ch in word if ch.strip())
        else:
            tokens.append(word)
    return tokens
