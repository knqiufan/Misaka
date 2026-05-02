"""LangChain-based text chunker adapter."""

from __future__ import annotations

import logging

from misaka.services.knowledge.rag.abstractions import ChunkData, TextChunker

logger = logging.getLogger(__name__)

# Separator list covering both Chinese and English punctuation.
_CJK_EN_SEPARATORS: list[str] = [
    "\n\n", "\n",
    "。", "！", "？", "；",
    ". ", "! ", "? ", "; ",
    " ", "",
]

_EXCEL_CHUNK_ROWS = 20


class LCTextChunker(TextChunker):
    """Split text using LangChain text-splitter strategies.

    Strategy per file type:
        txt / docx / pdf → RecursiveCharacterTextSplitter (CJK + EN)
        markdown         → MarkdownHeaderTextSplitter → RecursiveCharacterTextSplitter
        xlsx             → Row-preserving custom chunker (every N rows with header)
    """

    def chunk(
        self,
        text: str,
        file_type: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        metadata: dict | None = None,
    ) -> list[ChunkData]:
        if not text or not text.strip():
            return []

        if file_type == "markdown":
            return self._chunk_markdown(text, chunk_size, chunk_overlap, metadata)
        if file_type == "xlsx":
            return self._chunk_excel(text, metadata)
        return self._chunk_recursive(text, chunk_size, chunk_overlap, metadata)

    # ------------------------------------------------------------------
    # Strategy: recursive character splitting (txt / docx / pdf)
    # ------------------------------------------------------------------

    def _chunk_recursive(
        self,
        text: str,
        chunk_size: int,
        chunk_overlap: int,
        metadata: dict | None,
    ) -> list[ChunkData]:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=_CJK_EN_SEPARATORS,
            length_function=len,
            is_separator_regex=False,
        )
        lc_docs = splitter.create_documents([text], metadatas=[metadata or {}])
        return self._to_chunk_data(lc_docs, text)

    # ------------------------------------------------------------------
    # Strategy: two-pass markdown splitting
    # ------------------------------------------------------------------

    def _chunk_markdown(
        self,
        text: str,
        chunk_size: int,
        chunk_overlap: int,
        metadata: dict | None,
    ) -> list[ChunkData]:
        from langchain_text_splitters import (
            MarkdownHeaderTextSplitter,
            RecursiveCharacterTextSplitter,
        )

        headers_to_split_on = [
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
        ]
        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False,
        )
        md_docs = md_splitter.split_text(text)

        char_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=_CJK_EN_SEPARATORS,
            length_function=len,
            is_separator_regex=False,
        )
        final_docs = char_splitter.split_documents(md_docs)

        base_meta = metadata or {}
        for doc in final_docs:
            doc.metadata = {**base_meta, **doc.metadata}

        return self._to_chunk_data(final_docs, text)

    # ------------------------------------------------------------------
    # Strategy: row-preserving excel chunking
    # ------------------------------------------------------------------

    def _chunk_excel(
        self,
        text: str,
        metadata: dict | None,
    ) -> list[ChunkData]:
        """Split tab-separated Excel text keeping rows intact.

        Each chunk includes the header row (first line) followed by up to
        ``_EXCEL_CHUNK_ROWS`` data rows.
        """
        lines = text.split("\n")
        if len(lines) <= 1:
            return [ChunkData(content=text, index=0, metadata=metadata or {})]

        header = lines[0]
        data_lines = lines[1:]
        chunks: list[ChunkData] = []

        for batch_start in range(0, len(data_lines), _EXCEL_CHUNK_ROWS):
            batch = data_lines[batch_start : batch_start + _EXCEL_CHUNK_ROWS]
            content = "\n".join([header, *batch])
            chunk_meta = {
                **(metadata or {}),
                "row_start": batch_start + 2,
                "row_end": batch_start + len(batch) + 1,
            }
            chunks.append(ChunkData(
                content=content,
                index=len(chunks),
                metadata=chunk_meta,
            ))

        return chunks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_chunk_data(lc_docs: list, source_text: str) -> list[ChunkData]:
        """Convert LangChain Document list into ChunkData list.

        Attempts to compute ``start_char`` / ``end_char`` by searching
        for each chunk's content within the source text.
        """
        results: list[ChunkData] = []
        search_from = 0
        for i, doc in enumerate(lc_docs):
            content = doc.page_content
            start = source_text.find(content, search_from)
            if start == -1:
                start = source_text.find(content)
            end = start + len(content) if start >= 0 else 0
            if start >= 0:
                search_from = start + 1

            results.append(ChunkData(
                content=content,
                index=i,
                start_char=max(start, 0),
                end_char=end,
                metadata=dict(doc.metadata),
            ))
        return results
