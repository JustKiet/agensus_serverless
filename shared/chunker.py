"""Markdown chunker for Lambda functions (sync version, ported from backend)."""

from langchain_text_splitters import MarkdownHeaderTextSplitter
from shared.models import ChunkItem

_headers_to_split_on = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3"),
    ("####", "H4"),
]


class MarkdownChunker:
    def __init__(
        self,
        headers_to_split_on: list[tuple[str, str]] | None = None,
    ) -> None:
        self.headers_to_split_on = headers_to_split_on or _headers_to_split_on
        self.splitter = MarkdownHeaderTextSplitter(self.headers_to_split_on)

    def chunk(self, text: str, document_id: str) -> list[ChunkItem]:
        documents = self.splitter.split_text(text)
        return [
            ChunkItem(
                document_id=document_id,
                text=doc.page_content,
                chunk_index=idx,
                metadata=doc.metadata,
            )
            for idx, doc in enumerate(documents)
        ]
