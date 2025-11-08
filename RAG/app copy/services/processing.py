from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List

from haystack import Document
from haystack.components.preprocessors import DocumentSplitter

from app.core.config import get_settings
from app.services.crawler import CrawledPage


def build_documents(pages: Iterable[CrawledPage]) -> List[Document]:
    """Convert crawled pages to Haystack Documents with metadata."""
    documents: List[Document] = []
    for page in pages:
        meta = {
            "url": page.url,
            "title": page.title,
            "last_modified": page.last_modified,
            "checksum": page.checksum,
        }
        documents.append(Document(content=page.text, meta=meta, id=page.checksum))
    return documents


@lru_cache(maxsize=1)
def get_document_splitter() -> DocumentSplitter:
    settings = get_settings()
    splitter = DocumentSplitter(
        split_by="word",
        split_length=settings.chunk_size,
        split_overlap=settings.chunk_overlap,
        respect_sentence_boundary=False,
        use_split_rules=False,
    )
    splitter.warm_up()
    return splitter
