from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from app.pipelines.ingestion import ingest_site
from app.pipelines.query import list_namespaces, run_query
from app.schemas.rag import Citation, IngestRequest, IngestResponse, QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint(request: IngestRequest) -> IngestResponse:
    # For now we run ingestion synchronously; swap to background_tasks.add_task
    # or Celery when productionizing.
    base_url = str(request.base_url) if request.base_url else None
    result = await ingest_site(base_url=base_url, namespace=request.namespace)
    return IngestResponse(**result)


@router.get("/namespaces")
async def list_namespaces_endpoint() -> list[dict[str, object]]:
    return list_namespaces()

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    try:
        result = run_query(
            question=request.question,
            namespace=request.namespace,
            filters=request.filters or {},
        )
    except Exception as exc:  # pragma: no cover - defensive API guard
        logger.exception("Query pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    answer_text = result.get("answer", "")
    documents: List = result.get("documents", [])
    if not answer_text:
        return QueryResponse(
            answer="No answer could be generated from the available documents.",
            citations=[],
        )

    citations: List[Citation] = []
    for idx, doc in enumerate(documents, start=1):
        meta = doc.meta or {}
        url = meta.get("url")
        if not url:
            continue
        snippet_raw = (doc.content or "").strip().splitlines()[0] if doc.content else ""
        snippet = snippet_raw.split(".")[0][:160].strip()
        if not snippet:
            snippet = "View source"
        citations.append(
            Citation(
                label=f"[{idx}]",
                url=url,
                snippet=snippet,
            )
        )

    return QueryResponse(answer=answer_text, citations=citations)
