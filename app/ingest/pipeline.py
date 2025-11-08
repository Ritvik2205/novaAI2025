from __future__ import annotations

import asyncio
import uuid
from typing import Any

from celery import Celery

from app.config import get_settings
from app.db import Chunk, Document, Embedding, session_scope
from app.ingest import crawl, chunk, label
from app.ingest.parse import ParsedDoc, parse_any
from app.search.elasticsearch import ElasticHelper
from app.search.embeddings import get_embedding_provider
from app.utils import minhash
from app.utils.logging import configure_logging

settings = get_settings()
celery_app = Celery(
    "nova",
    broker=settings.celery_broker_url or settings.redis_url,
    backend=settings.celery_result_backend or settings.redis_url,
)
logger = configure_logging(settings.log_level)
_elastic = ElasticHelper()
_elastic.ensure_index()
_embedder = get_embedding_provider()
_signatures: list[list[int]] = []


def _store_document(tenant_id: int, source_type: str, url: str, text: str, meta: dict[str, Any]) -> list[Chunk]:
    created: list[Chunk] = []
    with session_scope() as session:
        doc = Document(
            tenant_id=tenant_id,
            source_type=source_type,
            url_or_name=url,
            mime=meta.get("doc_type", "text/plain"),
            sha256=str(uuid.uuid4()),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        for ch in chunk.chunk_text(text, url=url, section=meta.get("section")):
            tags = label.fast_label(ch["text"])
            ch_meta = {**ch["meta"], "labels": tags}
            signature = minhash.minhash_signature(ch["text"])
            if minhash.is_near_duplicate(ch["text"], _signatures):
                continue
            _signatures.append(signature)
            rec = Chunk(document_id=doc.id, text=ch["text"], meta_json=ch_meta)
            session.add(rec)
            session.commit()
            session.refresh(rec)
            created.append(rec)
            _elastic.index_chunk(
                rec.id,
                tenant_id,
                {
                    "text": rec.text,
                    "doc_type": ch_meta.get("labels", ["marketing"])[0],
                    "url": ch_meta.get("url"),
                    "section": ch_meta.get("section"),
                },
            )
    return created


@celery_app.task
def ingest_website_task(job_id: str, tenant_id: int, start_url: str, allowlist: list[str] | None, denylist: list[str] | None) -> dict[str, Any]:
    logger.info("ingest website job=%s tenant=%s", job_id, tenant_id)
    chunks_indexed = 0
    async def runner():
        nonlocal chunks_indexed
        async for url, text, meta in crawl.crawl(start_url, allowlist, denylist):
            created_chunks = _store_document(tenant_id, "web", url, text, meta)
            if not created_chunks:
                continue
            vectors = _embedder.embed([ch.text for ch in created_chunks])
            with session_scope() as session:
                for ch, vector in zip(created_chunks, vectors):
                    session.add(Embedding(chunk_id=ch.id, vector=vector))
                session.commit()
            chunks_indexed += len(created_chunks)
    asyncio.run(runner())
    return {"job_id": job_id, "chunks": chunks_indexed}


@celery_app.task
def ingest_upload_task(job_id: str, tenant_id: int, file_path: str) -> dict[str, Any]:
    parsed: ParsedDoc = parse_any(file_path)
    created_chunks = _store_document(tenant_id, "upload", file_path, parsed.text, parsed.meta)
    vectors = _embedder.embed([ch.text for ch in created_chunks])
    with session_scope() as session:
        for ch, vector in zip(created_chunks, vectors):
            session.add(Embedding(chunk_id=ch.id, vector=vector))
        session.commit()
    return {"job_id": job_id, "chunks": len(created_chunks)}


def enqueue_website_ingest(payload: dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    ingest_website_task.delay(job_id, payload["tenant_id"], payload["start_url"], payload.get("allowlist"), payload.get("denylist"))
    return job_id


def enqueue_upload_ingest(tenant_id: int, file_path: str) -> str:
    job_id = str(uuid.uuid4())
    ingest_upload_task.delay(job_id, tenant_id, file_path)
    return job_id
