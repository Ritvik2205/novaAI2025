"""
Client wrapper around the OpenRouter chat completions API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class OpenRouterError(RuntimeError):
    """Raised when the OpenRouter API returns an error."""


class OpenRouterClient:
    """Lightweight synchronous client for OpenRouter."""

    def __init__(self, api_key: str, base_url: str):
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for agent conversations.")
        self.api_key = api_key
        self.base_url = base_url

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        max_tokens: int = 1200,
        temperature: float = 0.2,
        extra_headers: Optional[Dict[str, str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Perform a chat completion call."""

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if metadata:
            payload["metadata"] = metadata

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://nova-agentic-crm.local",
            "X-Title": "Agentic CRM Builder",
        }
        if extra_headers:
            headers.update(extra_headers)

        response = requests.post(self.base_url, json=payload, headers=headers, timeout=60)
        if response.status_code >= 400:
            logger.error("OpenRouter error %s: %s", response.status_code, response.text)
            raise OpenRouterError(f"OpenRouter request failed: {response.text}")

        result = response.json()
        if "choices" not in result:
            raise OpenRouterError(f"Unexpected response payload: {result}")
        return result["choices"][0]["message"]

