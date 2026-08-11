"""Validation of malformed third-party reranker responses."""

from __future__ import annotations

import pytest

from misaka.services.knowledge.rag.abstractions import RerankerConfig, RetrievalResult
from misaka.services.knowledge.rag.langchain.reranker import LCReranker


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "results": [
                {"index": -1, "relevance_score": 99},
                {"index": 99, "relevance_score": 99},
                {"index": 1, "relevance_score": "0.8"},
                {"index": 1, "relevance_score": 0.7},
                {"index": 0, "relevance_score": "not-a-number"},
            ],
        }


class _Client:
    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        return None

    async def post(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _Response()


async def test_reranker_discards_invalid_and_duplicate_indexes(monkeypatch) -> None:
    monkeypatch.setattr(
        "misaka.services.knowledge.rag.langchain.reranker.httpx.AsyncClient",
        _Client,
    )
    results = [
        RetrievalResult("a", "first", 0.1),
        RetrievalResult("b", "second", 0.2),
    ]

    reranked = await LCReranker().rerank(
        "query",
        results,
        RerankerConfig("rank", "https://example.test", "key"),
    )

    assert [(result.chunk_id, result.score) for result in reranked] == [("b", 0.8)]


async def test_reranker_fails_closed_when_no_valid_indexes(monkeypatch) -> None:
    class _InvalidResponse(_Response):
        def json(self) -> dict:
            return {"results": [{"index": -1}, {"index": "one"}]}

    class _InvalidClient(_Client):
        async def post(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return _InvalidResponse()

    monkeypatch.setattr(
        "misaka.services.knowledge.rag.langchain.reranker.httpx.AsyncClient",
        _InvalidClient,
    )

    with pytest.raises(ValueError, match="no valid"):
        await LCReranker().rerank(
            "query",
            [RetrievalResult("a", "first", 0.1)],
            RerankerConfig("rank", "https://example.test", "key"),
        )
