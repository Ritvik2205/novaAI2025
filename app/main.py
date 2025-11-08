from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.middleware.guardrails import GuardrailMiddleware
from app.routes import auth, ingest, lead, query, quotes, tenant
from app.utils.logging import configure_logging

settings = get_settings()
logger = configure_logging(settings.log_level)

app = FastAPI(title="NOVA RAG")
app.add_middleware(GuardrailMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(tenant.router)
app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(lead.router)
app.include_router(quotes.router)


@app.get("/health")
def health() -> dict[str, str]:
    logger.info("health check")
    return {"status": "ok"}
