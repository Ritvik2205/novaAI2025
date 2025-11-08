from __future__ import annotations

import logging
from typing import Optional

from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.components.writers import DocumentWriter
from haystack.document_stores.types import DuplicatePolicy

from app.core.config import get_settings
from app.core.document_store import get_document_store
from app.services.crawler import SiteCrawler
from app.services.processing import build_documents, get_document_splitter

logger = logging.getLogger(__name__)


async def ingest_site(
    base_url: Optional[str],
    namespace: Optional[str] = None,
) -> dict:
    """Crawl and index a website into the configured vector store."""
    settings = get_settings()
    target_url = base_url or settings.default_base_url
    if not target_url:
        raise ValueError("No base_url provided and no default configured.")

    logger.info("Starting crawl for %s", target_url)
    crawler = SiteCrawler(
        base_url=target_url,
        max_pages=settings.crawler_max_pages,
        max_depth=settings.crawler_max_depth,
        concurrency=settings.crawler_concurrency,
        timeout=settings.crawler_timeout,
    )
    pages = await crawler.crawl()
    if not pages:
        logger.warning("Crawl produced no pages for %s", target_url)
        return {"pages_indexed": 0, "chunks_indexed": 0}

    documents = build_documents(pages)
    for doc in documents:
        doc.meta["base_url"] = target_url
        if namespace:
            doc.meta["namespace"] = namespace

    splitter = get_document_splitter()
    split_result = splitter.run(documents=documents)
    processed_docs = split_result["documents"]

    document_store = get_document_store(namespace=namespace)

    if not settings.openai_api_key.get_secret_value():
        raise RuntimeError("OPENAI_API_KEY must be set to compute embeddings.")

    embedder = OpenAIDocumentEmbedder(model=settings.openai_embedding_model)
    embed_result = embedder.run(documents=processed_docs)
    embedded_docs = embed_result["documents"]

    writer = DocumentWriter(document_store=document_store, policy=DuplicatePolicy.OVERWRITE)
    writer.run(documents=embedded_docs)

    logger.info(
        "Completed ingestion for %s (pages=%s, chunks=%s)",
        target_url,
        len(pages),
        len(processed_docs),
    )
    return {"pages_indexed": len(pages), "chunks_indexed": len(processed_docs)}
