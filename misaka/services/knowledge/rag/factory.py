"""RAG component factory — single entry point for framework switching.

All ``create_*`` methods use **lazy imports** so that missing framework
dependencies (e.g. LangChain) only trigger an error when a component is
actually requested, not at module-import time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from misaka.services.knowledge.rag.abstractions import (
    DocumentParser,
    EmbeddingProvider,
    Reranker,
    Retriever,
    TextChunker,
    VectorStore,
)


class RAGComponentFactory:
    """Create RAG components for the configured backend.

    Parser, chunker, embedding, and reranker components remain LangChain
    adapters. Only vector storage and retrieval vary by backend.
    """

    def __init__(
        self,
        db_path: str,
        backend: str = "langchain",
        seekdb_mode: str = "",
        seekdb_config: dict[str, Any] | None = None,
    ) -> None:
        self._db_path = db_path
        self._backend = backend
        self._seekdb_mode = seekdb_mode
        self._seekdb_config = seekdb_config

    def create_parser(self) -> DocumentParser:
        from .langchain.parser import LCDocumentParser
        return LCDocumentParser()

    def create_chunker(self) -> TextChunker:
        from .langchain.chunker import LCTextChunker
        return LCTextChunker()

    def create_embedding_provider(self) -> EmbeddingProvider:
        from .langchain.embedding import LCEmbeddingProvider
        return LCEmbeddingProvider()

    def create_vector_store(self) -> VectorStore:
        if self._backend == "langchain":
            from .langchain.vector_store import LCSqliteVecStore
            return LCSqliteVecStore(self._db_path)
        if self._backend == "seekdb":
            from .seekdb.vector_store import SeekDBVectorStore
            return SeekDBVectorStore(
                mode=self._seekdb_mode,
                embedded_path=str(Path(self._db_path).parent / "seekdb"),
                remote_config=self._seekdb_config,
            )
        raise ValueError(f"Unknown backend: {self._backend}")

    def create_retriever(self, vector_store: VectorStore) -> Retriever:
        if self._backend == "langchain":
            from .langchain.retriever import LCHybridRetriever
            return LCHybridRetriever(vector_store)
        if self._backend == "seekdb":
            from .seekdb.retriever import SeekDBHybridRetriever
            from .seekdb.vector_store import SeekDBVectorStore
            if not isinstance(vector_store, SeekDBVectorStore):
                raise TypeError("SeekDB backend requires SeekDBVectorStore")
            return SeekDBHybridRetriever(vector_store)
        raise ValueError(f"Unknown backend: {self._backend}")

    def create_reranker(self) -> Reranker:
        from .langchain.reranker import LCReranker
        return LCReranker()
