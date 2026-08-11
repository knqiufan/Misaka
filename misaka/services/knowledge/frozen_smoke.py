"""Self-contained RAG smoke test for a PyInstaller distribution."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from misaka.services.knowledge.rag.abstractions import ChunkData
from misaka.services.knowledge.rag.langchain.retriever import LCHybridRetriever
from misaka.services.knowledge.rag.langchain.vector_store import LCSqliteVecStore


def run_frozen_rag_smoke() -> None:
    """Exercise sqlite-vec load/write/search and NumPy-backed BM25 fusion."""
    with tempfile.TemporaryDirectory(prefix="misaka-rag-smoke-") as temp_dir:
        db_path = str(Path(temp_dir) / "vectors.sqlite3")
        store = LCSqliteVecStore(db_path)
        table_name = "smoke_vectors"
        chunks = [
            ChunkData(
                content="Misaka knowledge base vector retrieval",
                index=0,
                metadata={"chunk_db_id": "chunk-a", "document_id": "smoke"},
            ),
            ChunkData(
                content="Unrelated calendar appointment notes",
                index=1,
                metadata={"chunk_db_id": "chunk-b", "document_id": "smoke"},
            ),
        ]
        try:
            store.ensure_table(table_name, 2)
            store.add_chunks(table_name, chunks, [[1.0, 0.0], [0.0, 1.0]])
            results = asyncio.run(
                LCHybridRetriever(store).retrieve(
                    "knowledge retrieval",
                    [1.0, 0.0],
                    table_name,
                    top_k=1,
                    chunks_for_bm25=chunks,
                )
            )
            if not results or results[0].content != chunks[0].content:
                raise RuntimeError("Frozen RAG smoke test returned no expected result")
        finally:
            store.close()
