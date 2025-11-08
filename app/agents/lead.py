from __future__ import annotations

import json
import uuid
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.actions import calendar, crm, email
from app.config import get_settings
from app.pricebook.engine import QuoteEngine
from app.pricebook.schema import PriceBook

PRICEBOOK_CACHE: dict[int, PriceBook] = {}
DEFAULT_PRICEBOOK_PATH = Path("pricebook/construction_pricebook.json")


def load_pricebook(tenant_id: int) -> PriceBook:
    if tenant_id in PRICEBOOK_CACHE:
        return PRICEBOOK_CACHE[tenant_id]
    data = json.loads(DEFAULT_PRICEBOOK_PATH.read_text())
    PRICEBOOK_CACHE[tenant_id] = PriceBook(**data)
    return PRICEBOOK_CACHE[tenant_id]


def ensure_state(state: dict | None) -> dict:
    if state is None:
        state = {"contact": {}, "project": {}, "decision": {}, "turns": []}
    return state


def _generate_pdf(data: dict) -> str:
    out_path = Path("tmp")
    out_path.mkdir(exist_ok=True)
    file_path = out_path / f"quote-{uuid.uuid4()}.pdf"
    c = canvas.Canvas(str(file_path), pagesize=letter)
    c.drawString(72, 720, "Quote Summary")
    c.drawString(72, 700, f"Total: ${data['total_low']:.0f}-${data['total_high']:.0f}")
    y = 660
    for assumption in data.get("assumptions", []):
        c.drawString(72, y, f"- {assumption}")
        y -= 20
    c.save()
    return str(file_path)


class LeadAgent:
    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self.pricebook = load_pricebook(tenant_id)
        self.settings = get_settings()

    def _update_slots(self, state: dict, text: str) -> None:
        lower = text.lower()
        state.setdefault("project", {})
        if "deck" in lower:
            state["project"]["scope"] = "Deck Construction"
        if any(token.isdigit() for token in text.split()):
            state["project"]["dimensions"] = text
        if "june" in lower:
            state.setdefault("decision", {})["timeline"] = "June"
        if "@" in text:
            state.setdefault("contact", {})["email"] = text.split()[0]

    def _next_question(self, state: dict) -> str | None:
        if "scope" not in state.get("project", {}):
            return "What type of project are you planning (deck, treehouse, etc.)?"
        if "dimensions" not in state["project"]:
            return "Do you have approximate dimensions or quantities?"
        if "email" not in state.get("contact", {}):
            return "What's the best email for your quote?"
        return None

    async def handle_turn(self, text: str, state: dict | None) -> tuple[dict, str | None, dict | None]:
        state = ensure_state(state)
        state.setdefault("turns", []).append({"from": "user", "text": text})
        self._update_slots(state, text)
        question = self._next_question(state)
        if question:
            state["turns"].append({"from": "assistant", "text": question})
            return state, question, None
        quote_payload = self._build_quote(state)
        state["turns"].append({"from": "assistant", "text": "Here is your estimate."})
        return state, None, quote_payload

    def _build_quote(self, state: dict) -> dict:
        project = state.get("project", {})
        scope = project.get("scope", "Deck Construction")
        quantity = 1 if "dimensions" not in project else max(len(project["dimensions"]), 1)
        engine = QuoteEngine(self.pricebook)
        estimate = engine.estimate(region="west", scope=scope, quantity=1)
        lead = crm.upsert_lead(self.tenant_id, state.get("contact", {}), project, state.get("decision", {}))
        crm.store_quote(lead.id, estimate.__dict__)
        pdf_url = _generate_pdf(estimate.__dict__)
        contact_email = state.get("contact", {}).get("email")
        email.send_quote_email(contact_email, "Your construction estimate", f"Low ${estimate.total_low:.0f}")
        slots = calendar.suggest_slots()
        return {
            "items": estimate.items,
            "total_low": estimate.total_low,
            "total_high": estimate.total_high,
            "assumptions": estimate.assumptions,
            "confidence": estimate.confidence,
            "calendar_slots": slots,
            "pdf_path": pdf_url,
        }
