from __future__ import annotations

import re
from typing import Literal

Intent = Literal["lead_quote", "qna", "other"]


PRICE_KEYWORDS = {"price", "quote", "cost", "estimate", "budget"}
LEAD_KEYWORDS = {"timeline", "availability", "book", "schedule"}


def heuristic_intent(text: str) -> Intent:
    lower = text.lower()
    if any(word in lower for word in PRICE_KEYWORDS | LEAD_KEYWORDS):
        return "lead_quote"
    if "who" in lower or "what" in lower or "how" in lower:
        return "qna"
    return "other"
