"""sqlite-vec based vector store adapter."""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import struct
import threading

from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    RetrievalResult,
    VectorStore,
)

logger = logging.getLogger(__name__)


def _serialize_f32(vec: list[float]) -> bytes:
    """Pack a float list into a compact ``float32`` binary blob."""
    return struct.pack(f"{len(vec)}f", *vec)


class LCSqliteVecStore(VectorStore):
    """Vector store backed by the ``sqlite-vec`` extension.

    Each knowledge base gets its own virtual table (``kb_vec_<prefix>``).
    Vectors are stored as compact float32 blobs for optimal performance.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ensure_table(self, table_name: str, dimensions: int) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS [{table_name}]
                USING vec0(
                    chunk_id TEXT PRIMARY KEY,
                    embedding float[{dimensions}]
                )
            """)
            self._ensure_metadata_table(conn, table_name)
            conn.commit()

    def add_chunks(
        self,
        table_name: str,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
    ) -> None:
        if not chunks:
            return
        with self._lock:
            conn = self._get_conn()
            self._insert_vectors(conn, table_name, chunks, embeddings)
            self._insert_metadata(conn, table_name, chunks)
            conn.commit()

    def search(
        self,
        table_name: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        with self._lock:
            conn = self._get_conn()
            meta_table = f"{table_name}_meta"

            query_blob = _serialize_f32(query_embedding)
            rows = conn.execute(
                f"""
                SELECT v.chunk_id, v.distance, m.content, m.metadata_json
                FROM [{table_name}] v
                LEFT JOIN [{meta_table}] m ON v.chunk_id = m.chunk_id
                WHERE v.embedding MATCH ?
                  AND k = ?
                ORDER BY v.distance
                """,
                (query_blob, top_k),
            ).fetchall()

            results: list[RetrievalResult] = []
            for row in rows:
                chunk_id = row[0]
                distance = float(row[1])
                score = 1.0 / (1.0 + distance)
                content = row[2] or ""
                metadata = json.loads(row[3]) if row[3] else {}

                results.append(RetrievalResult(
                    chunk_id=chunk_id,
                    content=content,
                    score=score,
                    metadata=metadata,
                ))
            return results

    def delete_by_ids(
        self,
        table_name: str,
        chunk_ids: list[str],
    ) -> None:
        if not chunk_ids:
            return
        with self._lock:
            conn = self._get_conn()
            meta_table = f"{table_name}_meta"
            placeholders = ",".join("?" for _ in chunk_ids)

            conn.execute(
                f"DELETE FROM [{table_name}] WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(
                    f"DELETE FROM [{meta_table}] WHERE chunk_id IN ({placeholders})",
                    chunk_ids,
                )
            conn.commit()

    def drop_table(self, table_name: str) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(f"DROP TABLE IF EXISTS [{table_name}]")
            conn.execute(f"DROP TABLE IF EXISTS [{table_name}_meta]")
            conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            # Searches run in ``asyncio.to_thread`` so the chat event loop can
            # honor the global retrieval deadline. The store serializes access
            # with ``_lock`` because this connection is shared across workers.
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.enable_load_extension(True)
            import sqlite_vec  # noqa: F401

            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
        return self._conn

    @staticmethod
    def _ensure_metadata_table(conn: sqlite3.Connection, table_name: str) -> None:
        """Create a companion table that stores chunk text and metadata.

        The vec0 virtual table only holds the vector; we need a side table
        for the textual content and JSON metadata.
        """
        meta_table = f"{table_name}_meta"
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS [{meta_table}] (
                chunk_id TEXT PRIMARY KEY,
                content TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{{}}'
            )
        """)

    @staticmethod
    def _get_chunk_id(chunk: ChunkData) -> str:
        """Resolve the chunk ID: prefer ``chunk_db_id`` in metadata, fallback to index."""
        return str(chunk.metadata.get("chunk_db_id", f"chunk_{chunk.index}"))

    @staticmethod
    def _insert_vectors(
        conn: sqlite3.Connection,
        table_name: str,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
    ) -> None:
        rows = [
            (LCSqliteVecStore._get_chunk_id(c), _serialize_f32(emb))
            for c, emb in zip(chunks, embeddings, strict=False)
        ]
        conn.executemany(
            f"INSERT INTO [{table_name}](chunk_id, embedding) VALUES (?, ?)",
            rows,
        )

    @staticmethod
    def _insert_metadata(
        conn: sqlite3.Connection,
        table_name: str,
        chunks: list[ChunkData],
    ) -> None:
        meta_table = f"{table_name}_meta"
        rows = [
            (
                LCSqliteVecStore._get_chunk_id(c),
                c.content,
                json.dumps(c.metadata, ensure_ascii=False),
            )
            for c in chunks
        ]
        ins_sql = (
            f"INSERT OR REPLACE INTO [{meta_table}]"
            "(chunk_id, content, metadata_json) VALUES (?, ?, ?)"
        )
        conn.executemany(ins_sql, rows)
