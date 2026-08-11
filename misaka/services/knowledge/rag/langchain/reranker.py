"""Reranker adapter using an OpenAI-compatible rerank API."""

from __future__ import annotations

import logging
import math

import httpx

from misaka.services.knowledge.rag.abstractions import (
    Reranker,
    RerankerConfig,
    RetrievalResult,
)

logger = logging.getLogger(__name__)

_RERANK_TIMEOUT = 30.0


class LCReranker(Reranker):
    """Call ``POST {base_url}/v1/rerank`` to re-rank retrieval results.

    The API is expected to follow the Cohere / Jina rerank schema::

        POST /v1/rerank
        {
            "model": "...",
            "query": "...",
            "documents": ["...", "..."],
            "top_n": 3
        }
    """

    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        config: RerankerConfig,
    ) -> list[RetrievalResult]:
        if not results:
            return []

        texts = [r.content for r in results]
        url = f"{config.base_url.rstrip('/')}/v1/rerank"

        async with httpx.AsyncClient(timeout=_RERANK_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model_id,
                    "query": query,
                    "documents": texts,
                    "top_n": config.top_n,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        reranked: list[RetrievalResult] = []
        seen_indices: set[int] = set()
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int) or isinstance(idx, bool):
                continue
            if idx < 0 or idx >= len(results) or idx in seen_indices:
                continue
            try:
                score = float(item.get("relevance_score", 0.0))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(score):
                continue
            seen_indices.add(idx)
            original = results[idx]
            reranked.append(RetrievalResult(
                chunk_id=original.chunk_id,
                content=original.content,
                score=score,
                metadata=original.metadata,
            ))

        if not reranked:
            raise ValueError("Reranker returned no valid result indices")
        reranked.sort(key=lambda r: r.score, reverse=True)
        return reranked
