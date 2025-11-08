from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db import Lead, Quote, session_scope
from app.utils.logging import configure_logging

logger = configure_logging()


@dataclass
class SimpleLead:
    id: int = 0


@dataclass
class SimpleQuote:
    id: int = 0


def upsert_lead(tenant_id: int, contact: dict[str, Any], project: dict[str, Any], decision: dict[str, Any]) -> Lead:
    try:
        with session_scope() as session:
            lead = Lead(
                tenant_id=tenant_id,
                contact_json=contact,
                project_json=project,
                decision_json=decision,
                status="captured",
                source="chat",
            )
            session.add(lead)
            session.commit()
            session.refresh(lead)
            logger.info("lead stored lead_id=%s", lead.id)
            return lead
    except Exception:
        logger.warning("db unavailable, returning stub lead")
        return SimpleLead()  # type: ignore[return-value]


def store_quote(lead_id: int, quote_payload: dict[str, Any]) -> Quote:
    try:
        with session_scope() as session:
            quote = Quote(
                lead_id=lead_id,
                items_json=quote_payload["items"],
                total_low=quote_payload["total_low"],
                total_high=quote_payload["total_high"],
                assumptions_json=quote_payload["assumptions"],
                confidence=quote_payload["confidence"],
                currency="USD",
            )
            session.add(quote)
            session.commit()
            session.refresh(quote)
            logger.info("quote stored quote_id=%s", quote.id)
            return quote
    except Exception:
        logger.warning("db unavailable, returning stub quote")
        return SimpleQuote()  # type: ignore[return-value]
