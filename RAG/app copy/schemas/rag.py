from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class IngestRequest(BaseModel):
    base_url: Optional[HttpUrl] = Field(
        default=None, description="Root URL of the website to ingest."
    )
    namespace: Optional[str] = Field(
        default=None,
        description="Optional namespace/tenant identifier (maps to vector store collection).",
    )


class IngestResponse(BaseModel):
    pages_indexed: int
    chunks_indexed: int


class QueryRequest(BaseModel):
    question: str = Field(description="The user query.")
    namespace: Optional[str] = Field(
        default=None,
        description="Optional namespace/tenant identifier used during ingestion.",
    )
    filters: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Optional metadata filters for retrieval (exact match).",
    )


class Citation(BaseModel):
    label: str
    url: HttpUrl
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
