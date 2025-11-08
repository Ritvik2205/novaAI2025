from __future__ import annotations

import hashlib
from typing import Iterable, Sequence


def _hash(token: str, seed: int) -> int:
    data = f"{seed}:{token}".encode("utf-8")
    return int(hashlib.sha1(data).hexdigest(), 16)


def shingles(text: str, size: int = 5) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(max(1, len(words) - size + 1))]


def minhash_signature(text: str, seeds: Sequence[int] = range(32)) -> list[int]:
    sh = shingles(text)
    if not sh:
        return [0 for _ in seeds]
    sig: list[int] = []
    for seed in seeds:
        sig.append(min(_hash(token, seed) for token in sh))
    return sig


def jaccard(sig_a: Sequence[int], sig_b: Sequence[int]) -> float:
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / max(len(sig_a), 1)


def is_near_duplicate(text: str, existing: Iterable[list[int]], threshold: float = 0.9) -> bool:
    sig = minhash_signature(text)
    for other in existing:
        if jaccard(sig, other) >= threshold:
            return True
    return False
