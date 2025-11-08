from __future__ import annotations

from typing import Iterable

LABELS = [
    "services",
    "pricing",
    "policy",
    "warranty",
    "legal",
    "case_study",
    "bio",
    "how_to",
    "faq",
    "marketing",
]


def fast_label(text: str) -> list[str]:
    lower = text.lower()
    tags: list[str] = []
    for label in LABELS:
        if label.replace("_", " ") in lower:
            tags.append(label)
    if not tags:
        if "price" in lower or "$" in lower:
            tags.append("pricing")
        else:
            tags.append("marketing")
    return tags
