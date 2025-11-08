from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    name: str
    region: str = Field(pattern="^(west|east|central)$")


class TenantResponse(BaseModel):
    tenant_id: int
    api_key: str


class WebsiteIngestRequest(BaseModel):
    tenant_id: int
    start_url: str
    allowlist: list[str] | None = None
    denylist: list[str] | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    detail: str | None = None


class QueryRequest(BaseModel):
    tenant_id: int
    query: str
    top_k: int = 5
    rerank: bool | None = None


class Citation(BaseModel):
    url: str | None = None
    section: str | None = None
    score: float | None = None


class RetrievedChunk(BaseModel):
    chunk_id: int
    text: str
    meta: dict[str, Any]
    score: float


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieved: list[RetrievedChunk]


class LeadDialogState(BaseModel):
    contact: dict[str, Any] = Field(default_factory=dict)
    project: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    turns: list[dict[str, Any]] = Field(default_factory=list)


class LeadAskRequest(BaseModel):
    tenant_id: int
    text: str
    dialog_state: LeadDialogState | None = None


class LeadAskResponse(BaseModel):
    dialog_state: LeadDialogState
    followup: str | None = None
    quote: dict[str, Any] | None = None


class LeadQuoteRequest(BaseModel):
    tenant_id: int
    dialog_state: LeadDialogState


class LeadQuoteResponse(BaseModel):
    quote: dict[str, Any]
    dialog_state: LeadDialogState
    pdf_url: str | None = None


class PricebookResponse(BaseModel):
    tenant_id: int
    pricebook: dict[str, Any]


class PricebookUpdateRequest(BaseModel):
    pricebook: dict[str, Any]


class AuditPayload(BaseModel):
    id: int
    tenant_id: int
    actor: str
    action: str
    created_at: datetime
