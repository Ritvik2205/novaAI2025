from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.pricebook.schema import PriceBook, Service


@dataclass
class QuoteEstimate:
    items: list[dict[str, Any]]
    total_low: float
    total_high: float
    assumptions: list[str]
    confidence: float


class QuoteEngine:
    def __init__(self, pricebook: PriceBook) -> None:
        self.pricebook = pricebook
        self.settings = get_settings()

    def _select_service(self, scope: str) -> Service:
        for service in self.pricebook.services:
            if service.name.lower().split()[0] in scope.lower():
                return service
        return self.pricebook.services[0]

    def estimate(self, region: str, scope: str, quantity: float, complexity: str | None = None) -> QuoteEstimate:
        service = self._select_service(scope)
        multiplier = service.regional_multiplier.get(region, 1.0)
        if complexity:
            for mod in service.complexity_mods:
                if mod["label"] in complexity:
                    multiplier *= mod.get("multiplier", 1.0)
        base = max(service.min_fee, service.base_rate * quantity * multiplier)
        high = base * 1.2
        assumptions = [f"Lead time ~{service.lead_time} days"]
        if high > self.settings.max_quote_cap:
            high = float(self.settings.max_quote_cap)
            assumptions.append("Quote capped for guardrails")
        confidence = 0.65 if base < self.settings.max_quote_cap else 0.5
        items = [
            {
                "name": service.name,
                "quantity": quantity,
                "unit": service.unit,
                "unit_rate": service.base_rate,
                "region_multiplier": multiplier,
            }
        ]
        return QuoteEstimate(items=items, total_low=base, total_high=high, assumptions=assumptions, confidence=confidence)
