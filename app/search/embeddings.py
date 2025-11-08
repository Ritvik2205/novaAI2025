from __future__ import annotations

import abc
import hashlib
import json
from typing import Iterable, List

import openai
import redis

from app.config import get_settings


class EmbeddingProvider(abc.ABC):
    @abc.abstractmethod
    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        openai.api_key = settings.openai_api_key
        self._cache = redis.from_url(settings.redis_url)
        self._local_fallback: dict[str, list[float]] = {}

    def _cache_key(self, text: str) -> str:
        return f"embed:{hashlib.sha1(text.encode()).hexdigest()}"

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        texts_list = list(texts)
        vectors: list[list[float]] = [None] * len(texts_list)  # type: ignore[list-item]
        missing: list[tuple[int, str]] = []
        for idx, text in enumerate(texts_list):
            key = self._cache_key(text)
            try:
                cached = self._cache.get(key)
            except Exception:
                cached = None
            if cached:
                vectors[idx] = json.loads(cached)
            elif key in self._local_fallback:
                vectors[idx] = self._local_fallback[key]
            else:
                missing.append((idx, text))
        if missing:
            response = openai.Embeddings.create(
                model="text-embedding-3-large",
                input=[text for _, text in missing],
            )
            embeddings = [data["embedding"] for data in response["data"]]
            for (idx, text), vec in zip(missing, embeddings):
                vectors[idx] = vec
                key = self._cache_key(text)
                try:
                    self._cache.setex(key, 60 * 60 * 24, json.dumps(vec))
                except Exception:
                    self._local_fallback[key] = vec
        return [vec or [0.0] for vec in vectors]


class LocalEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        # Cheap hash-based embedding for offline tests
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha1(text.encode()).digest()
            vectors.append([b / 255 for b in digest[:32]])
        return vectors


def get_embedding_provider() -> EmbeddingProvider:
    provider = get_settings().embedding_provider
    if provider == "local":
        return LocalEmbeddingProvider()
    settings = get_settings()
    if not settings.openai_api_key:
        return LocalEmbeddingProvider()
    return OpenAIEmbeddingProvider()
