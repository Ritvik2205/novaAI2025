from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Generator

from functools import lru_cache

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import get_settings


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    api_key_hash: str
    region: str
    settings_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id")
    source_type: str = Field(description="web|upload")
    url_or_name: str
    mime: str
    sha256: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id")
    text: str
    meta_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Embedding(SQLModel, table=True):
    __tablename__ = "embeddings"

    chunk_id: int = Field(foreign_key="chunks.id", primary_key=True)
    vector: list[float] = Field(sa_column=Column(Vector(3072)))


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id")
    contact_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    project_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    decision_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    status: str = Field(default="new")
    score: float | None = None
    source: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Quote(SQLModel, table=True):
    __tablename__ = "quotes"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="leads.id")
    items_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))
    total_low: float
    total_high: float
    assumptions_json: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    confidence: float
    currency: str = Field(default="USD")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Audit(SQLModel, table=True):
    __tablename__ = "audits"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id")
    actor: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    connect_args = {}
    engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            pass
    return engine


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    engine = get_engine()
    with Session(engine) as session:
        yield session


def session_scope() -> Session:
    return Session(get_engine())


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def fetch_tenant_by_key(session: Session, api_key: str) -> Tenant | None:
    hashed = hash_api_key(api_key)
    statement = select(Tenant).where(Tenant.api_key_hash == hashed)
    return session.exec(statement).first()


AsyncSessionType = AsyncSession
