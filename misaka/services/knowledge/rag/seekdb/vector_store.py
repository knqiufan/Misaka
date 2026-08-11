"""SeekDB-backed vector store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    RetrievalResult,
    VectorStore,
)

_VALID_MODES = {"seekdb_embedded", "seekdb_remote"}


class SeekDBVectorStore(VectorStore):
    """Store externally generated embeddings in a pyseekdb collection."""

    def __init__(
        self,
        mode: str,
        embedded_path: str = "",
        remote_config: dict[str, Any] | None = None,
    ) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"Unknown SeekDB mode: {mode}")
        self._mode = mode
        self._embedded_path = embedded_path
        self._remote_config = remote_config or {}
        self._client: Any | None = None

    def ensure_table(self, table_name: str, dimensions: int) -> None:
        import pyseekdb

        hnsw = pyseekdb.HNSWConfiguration(dimension=dimensions, distance="cosine")
        configuration_class = getattr(pyseekdb, "Configuration", None)
        configuration = configuration_class(hnsw=hnsw) if configuration_class else hnsw
        self._get_client().get_or_create_collection(
            name=table_name,
            configuration=configuration,
            embedding_function=None,
        )

    def add_chunks(
        self,
        table_name: str,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError(
                "Chunk/vector count mismatch: "
                f"received {len(chunks)} chunks and {len(embeddings)} embeddings"
            )
        if not chunks:
            return
        collection = self._get_collection(table_name)
        collection.upsert(
            ids=[self._get_chunk_id(chunk) for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk.content for chunk in chunks],
            metadatas=[dict(chunk.metadata) for chunk in chunks],
        )
        refresh_index = getattr(collection, "refresh_index", None)
        if callable(refresh_index):
            refresh_index()

    def search(
        self,
        table_name: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        results = self._get_collection(table_name).query(
            query_embeddings=query_embedding,
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        return self.convert_results(results)

    def delete_by_ids(self, table_name: str, chunk_ids: list[str]) -> None:
        if chunk_ids:
            self._get_collection(table_name).delete(ids=chunk_ids)

    def drop_table(self, table_name: str) -> None:
        client = self._get_client()
        # Callers use failures to enqueue durable cleanup work.  Suppressing
        # remote deletion errors here previously made orphaned vectors look
        # successfully deleted.
        client.delete_collection(table_name)

    def close(self) -> None:
        client = self._client
        self._client = None
        close = getattr(client, "close", None)
        if callable(close):
            close()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        import pyseekdb

        if self._mode == "seekdb_embedded":
            path = Path(self._embedded_path)
            path.mkdir(parents=True, exist_ok=True)
            self._client = pyseekdb.Client(
                path=str(path),
                database="misaka_kb",
            )
        else:
            config = self._remote_config
            host = str(config.get("host", "")).strip()
            if not host:
                raise ValueError("SeekDB remote host is required")
            self._client = pyseekdb.Client(
                host=host,
                port=int(config.get("port", 2881)),
                user=str(config.get("user", "root")),
                password=str(config.get("password", "")),
                database=str(config.get("database_name", "misaka_kb")),
            )
        return self._client

    def _get_collection(self, table_name: str) -> Any:
        return self._get_client().get_collection(
            table_name,
            embedding_function=None,
        )

    @staticmethod
    def _get_chunk_id(chunk: ChunkData) -> str:
        return str(chunk.metadata.get("chunk_db_id", f"chunk_{chunk.index}"))

    @staticmethod
    def convert_results(results: dict[str, Any]) -> list[RetrievalResult]:
        """Convert pyseekdb's query-compatible result shape."""
        ids = _first_result_list(results.get("ids"))
        documents = _first_result_list(results.get("documents"))
        metadatas = _first_result_list(results.get("metadatas"))
        distances = _first_result_list(results.get("distances"))

        converted: list[RetrievalResult] = []
        for index, chunk_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else float(index)
            converted.append(
                RetrievalResult(
                    chunk_id=str(chunk_id),
                    content=str(documents[index] or "") if index < len(documents) else "",
                    score=1.0 / (1.0 + max(distance, 0.0)),
                    metadata=(
                        dict(metadatas[index] or {})
                        if index < len(metadatas)
                        else {}
                    ),
                )
            )
        return converted


def _first_result_list(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else value
