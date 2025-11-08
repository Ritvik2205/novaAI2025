from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

TOKEN_TARGET = 600


def chunk_text(text: str, url: str | None = None, section: str | None = None, page: int | None = None) -> list[dict[str, object]]:
    words = text.split()
    chunks: list[dict[str, object]] = []
    for start in range(0, len(words), TOKEN_TARGET):
        window = words[start : start + TOKEN_TARGET]
        if not window:
            continue
        chunk_text = " ".join(window)
        chunks.append(
            {
                "text": chunk_text,
                "meta": {
                    "url": url,
                    "section": section,
                    "page": page,
                    "quote_relevant": "quote" in (section or "").lower(),
                },
            }
        )
    return chunks
