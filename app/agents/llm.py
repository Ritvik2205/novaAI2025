from __future__ import annotations

import abc
import hashlib
import json

import asyncio

import openai
import redis

from app.config import get_settings


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    async def chat(self, prompt: str) -> str:
        raise NotImplementedError


class OpenAILLMProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing")
        openai.api_key = settings.openai_api_key
        self._cache = redis.from_url(settings.redis_url)

    async def chat(self, prompt: str) -> str:
        key = hashlib.sha1(prompt.encode()).hexdigest()
        cached = self._cache.get(key)
        if cached:
            return cached.decode()
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Answer customer questions with citations."},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message["content"].strip()
        self._cache.setex(key, 3600, text)
        return text


class LocalLLMProvider(LLMProvider):
    async def chat(self, prompt: str) -> str:
        return prompt.split("\n")[-1][:400]


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.embedding_provider == "local" or not settings.openai_api_key:
        return LocalLLMProvider()
    return OpenAILLMProvider()
