"""Tests for the optional SeekDB vector-store adapters."""

from __future__ import annotations

import sys
from types import ModuleType

from misaka.services.knowledge.rag.abstractions import ChunkData
from misaka.services.knowledge.rag.factory import RAGComponentFactory
from misaka.services.knowledge.rag.seekdb.retriever import SeekDBHybridRetriever
from misaka.services.knowledge.rag.seekdb.vector_store import SeekDBVectorStore


class FakeCollection:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.documents: list[str] = []
        self.metadatas: list[dict] = []
        self.hybrid_calls: list[dict] = []
        self.refreshed = False

    def upsert(self, *, ids, embeddings, documents, metadatas) -> None:
        self.ids = list(ids)
        self.documents = list(documents)
        self.metadatas = list(metadatas)

    def refresh_index(self) -> None:
        self.refreshed = True

    def query(self, **kwargs):
        return self._results()

    def hybrid_search(self, **kwargs):
        self.hybrid_calls.append(kwargs)
        return self._results()

    def delete(self, *, ids) -> None:
        remove = set(ids)
        retained = [
            (item_id, document, metadata)
            for item_id, document, metadata in zip(
                self.ids,
                self.documents,
                self.metadatas,
                strict=False,
            )
            if item_id not in remove
        ]
        self.ids = [item[0] for item in retained]
        self.documents = [item[1] for item in retained]
        self.metadatas = [item[2] for item in retained]

    def _results(self) -> dict:
        return {
            "ids": [self.ids],
            "documents": [self.documents],
            "metadatas": [self.metadatas],
            "distances": [[0.1 + index for index in range(len(self.ids))]],
        }


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.collections: dict[str, FakeCollection] = {}
        self.closed = False
        self.__class__.instances.append(self)

    def get_or_create_collection(self, name, **kwargs):
        return self.collections.setdefault(name, FakeCollection())

    def get_collection(self, name, **kwargs):
        return self.collections[name]

    def delete_collection(self, name) -> None:
        self.collections.pop(name, None)

    def close(self) -> None:
        self.closed = True


def _install_fake_pyseekdb(monkeypatch) -> None:
    module = ModuleType("pyseekdb")

    class Configuration:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class HNSWConfiguration:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    module.Client = FakeClient
    module.Configuration = Configuration
    module.HNSWConfiguration = HNSWConfiguration
    monkeypatch.setitem(sys.modules, "pyseekdb", module)
    FakeClient.instances.clear()


def test_seekdb_vector_store_crud(monkeypatch, tmp_path) -> None:
    _install_fake_pyseekdb(monkeypatch)
    store = SeekDBVectorStore(
        mode="seekdb_remote",
        remote_config={
            "host": "localhost",
            "port": 2881,
            "user": "root",
            "password": "",
            "database_name": "misaka_kb",
        },
    )
    chunks = [
        ChunkData(
            content="SeekDB stores vectors",
            index=0,
            metadata={"chunk_db_id": "chunk-1", "document_id": "doc-1"},
        )
    ]

    store.ensure_table("kb_vec_test", 2)
    store.add_chunks("kb_vec_test", chunks, [[1.0, 0.0]])
    results = store.search("kb_vec_test", [1.0, 0.0])

    collection = FakeClient.instances[0].collections["kb_vec_test"]
    assert collection.refreshed is True
    assert results[0].chunk_id == "chunk-1"
    assert results[0].content == "SeekDB stores vectors"
    assert results[0].metadata["document_id"] == "doc-1"

    store.delete_by_ids("kb_vec_test", ["chunk-1"])
    assert collection.ids == []
    store.drop_table("kb_vec_test")
    assert "kb_vec_test" not in FakeClient.instances[0].collections
    store.close()
    assert FakeClient.instances[0].closed is True


async def test_seekdb_retriever_uses_native_hybrid_search(monkeypatch) -> None:
    _install_fake_pyseekdb(monkeypatch)
    store = SeekDBVectorStore(
        mode="seekdb_remote",
        remote_config={"host": "localhost"},
    )
    store.ensure_table("kb_vec_test", 2)
    store.add_chunks(
        "kb_vec_test",
        [ChunkData("hybrid result", 0, metadata={"chunk_db_id": "chunk-1"})],
        [[1.0, 0.0]],
    )

    retriever = SeekDBHybridRetriever(store)
    results = await retriever.retrieve(
        query="hybrid",
        query_embedding=[1.0, 0.0],
        table_name="kb_vec_test",
        top_k=3,
    )

    collection = FakeClient.instances[0].collections["kb_vec_test"]
    assert results[0].content == "hybrid result"
    assert collection.hybrid_calls[0]["rank"]["rrf"]["rank_constant"] == 60


def test_factory_switches_only_vector_components(tmp_path) -> None:
    factory = RAGComponentFactory(
        str(tmp_path / "misaka.db"),
        backend="seekdb",
        seekdb_mode="seekdb_embedded",
    )

    store = factory.create_vector_store()
    retriever = factory.create_retriever(store)

    assert isinstance(store, SeekDBVectorStore)
    assert isinstance(retriever, SeekDBHybridRetriever)
    assert factory.create_parser().__class__.__name__ == "LCDocumentParser"
    assert factory.create_chunker().__class__.__name__ == "LCTextChunker"
