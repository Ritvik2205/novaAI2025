import asyncio

from celery import Celery

from app.core.config import get_settings
from app.pipelines.ingestion import ingest_site

settings = get_settings()

celery_app = Celery(
    "venture_ingestion",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


@celery_app.task(name="ingest_site")
def ingest_site_task(base_url: str, namespace: str | None = None) -> dict:
    """Celery task wrapper for the ingestion pipeline."""
    return asyncio.run(ingest_site(base_url=base_url, namespace=namespace))

