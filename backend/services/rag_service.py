"""
Vector store backed retrieval using Chroma DB and the adapted SiteCrawler.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import chromadb
from chromadb.api import Collection
from chromadb.api.types import EmbeddingFunction
from sentence_transformers import SentenceTransformer

from backend.rag.site_crawler import SiteCrawler, CrawledPage

logger = logging.getLogger(__name__)


class SentenceTransformerEmbeddings(EmbeddingFunction):
    """Adapts sentence-transformers model to Chroma embedding function API."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        logger.info("Loading sentence transformer model %s", model_name)
        self.model = SentenceTransformer(model_name)

    def __call__(self, inputs: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(inputs, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()


@dataclass
class DocumentPayload:
    doc_id: str
    text: str
    metadata: Dict[str, str]


class RAGService:
    """Manage retrieval augmented knowledge per company."""

    def __init__(self, persist_path: Path, embedder_model: str, chunk_size: int, chunk_overlap: int):
        self.persist_path = persist_path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.client = chromadb.PersistentClient(path=str(persist_path))
        self.embedding_fn = SentenceTransformerEmbeddings(embedder_model)

    # ------------------------------------------------------------------
    # Collection helpers
    # ------------------------------------------------------------------
    def _collection_name(self, company_id: str) -> str:
        return f"company_{company_id}"

    def _get_collection(self, company_id: str) -> Collection:
        return self.client.get_or_create_collection(
            name=self._collection_name(company_id),
            embedding_function=self.embedding_fn,
            metadata={"company_id": company_id},
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def ingest_documents(self, company_id: str, documents: Iterable[DocumentPayload]) -> int:
        """Ingest raw documents already converted to text."""

        collection = self._get_collection(company_id)

        ids: List[str] = []
        texts: List[str] = []
        metadatas: List[Dict[str, str]] = []

        for document in documents:
            chunks = self._chunk_text(document.text)
            for index, chunk in enumerate(chunks):
                chunk_id = f"{document.doc_id}-{index}"
                ids.append(chunk_id)
                texts.append(chunk)
                chunk_meta = dict(document.metadata)
                chunk_meta.update({"chunk_index": str(index)})
                metadatas.append(chunk_meta)

        if not ids:
            return 0

        logger.info("Upserting %s chunks into vector store", len(ids))
        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
        return len(ids)

    async def _crawl_single(self, url: str) -> List[CrawledPage]:
        crawler = SiteCrawler(url)
        return await crawler.crawl()

    def ingest_urls(self, company_id: str, urls: Iterable[str]) -> Dict[str, int]:
        """Crawl and ingest multiple URLs."""

        unique_urls = list(dict.fromkeys(urls))
        if not unique_urls:
            return {"pages": 0, "chunks": 0}

        async def gather_pages() -> List[CrawledPage]:
            tasks = [self._crawl_single(url) for url in unique_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            pages: List[CrawledPage] = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error("Crawler error: %s", result)
                    continue
                pages.extend(result)
            return pages

        try:
            pages = asyncio.run(gather_pages())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            pages = loop.run_until_complete(gather_pages())

        payloads = [
            DocumentPayload(
                doc_id=page.checksum,
                text=page.text,
                metadata={
                    "source": "website",
                    "url": page.url,
                    "title": page.title,
                    "status_code": str(page.status_code),
                },
            )
            for page in pages
        ]
        chunks = self.ingest_documents(company_id, payloads)
        return {"pages": len(pages), "chunks": chunks}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def query(self, company_id: str, question: str, limit: int = 4) -> Dict[str, List[Dict[str, str]]]:
        collection = self._get_collection(company_id)
        results = collection.query(query_texts=[question], n_results=limit)
        context: List[Dict[str, str]] = []

        for doc, metadata in zip(results.get("documents", [[]])[0], results.get("metadatas", [[]])[0]):
            context.append({"text": doc, **(metadata or {})})

        return {"context": context}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _chunk_text(self, text: str) -> List[str]:
        words = text.split()
        if not words:
            return []
        chunks: List[str] = []
        step = self.chunk_size - self.chunk_overlap
        for start in range(0, len(words), step):
            end = min(start + self.chunk_size, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            if end == len(words):
                break
        return chunks

