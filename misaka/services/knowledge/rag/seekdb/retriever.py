"""SeekDB native hybrid retriever adapter."""

from __future__ import annotations

from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    RetrievalResult,
    Retriever,
)
from misaka.services.knowledge.rag.seekdb.vector_store import SeekDBVectorStore


class SeekDBHybridRetriever(Retriever):
    """Fuse SeekDB full-text and vector routes with native RRF ranking."""

    def __init__(self, vector_store: SeekDBVectorStore) -> None:
        self._store = vector_store

    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        table_name: str,
        top_k: int = 5,
        chunks_for_bm25: list[ChunkData] | None = None,
    ) -> list[RetrievalResult]:
        collection = self._store._get_collection(table_name)
        if not query.strip():
            return self._store.search(table_name, query_embedding, top_k)

        results = collection.hybrid_search(
            query={
                "where_document": {"$contains": query},
            },
            knn={
                "query_embeddings": [query_embedding],
                "n_results": top_k * 2,
            },
            rank={
                "rrf": {
                    "rank_window_size": max(top_k * 4, 20),
                    "rank_constant": 60,
                }
            },
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        return self._store.convert_results(results)
