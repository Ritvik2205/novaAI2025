"""
Integration hooks for Agentuity agent hosting.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class AgentuityClient:
    """Best-effort client for Agentuity. Falls back gracefully when disabled."""

    def __init__(self, api_key: str, base_url: Optional[str]):
        self.api_key = api_key
        self.base_url = base_url
        self.enabled = bool(api_key and base_url)
        if not self.enabled:
            logger.info("Agentuity integration disabled (missing API key or base URL).")

    def _headers(self) -> Dict[str, str]:
        if not self.enabled:
            raise RuntimeError("Agentuity integration is disabled.")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def sync_agent(self, definition: Dict[str, Any]) -> Optional[str]:
        """Create or update an agent definition on Agentuity."""

        if not self.enabled:
            logger.debug("Skipping Agentuity sync because integration is disabled.")
            return None

        response = requests.post(
            f"{self.base_url}/agents:sync",
            json=definition,
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code >= 400:
            logger.error("Agentuity sync failed (%s): %s", response.status_code, response.text)
            return None
        payload = response.json()
        agent_id = payload.get("agent_id") or payload.get("id")
        logger.info("Synced agent definition to Agentuity (agent_id=%s)", agent_id)
        return agent_id

    def create_handoff_session(self, agent_id: str, context: Dict[str, Any]) -> Optional[str]:
        """Request Agentuity to host a live agent session."""

        if not self.enabled:
            logger.debug("Skipping Agentuity handoff because integration is disabled.")
            return None

        response = requests.post(
            f"{self.base_url}/agents/{agent_id}/sessions",
            json=context,
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code >= 400:
            logger.error("Agentuity session creation failed (%s): %s", response.status_code, response.text)
            return None
        payload = response.json()
        session_id = payload.get("session_id") or payload.get("id")
        logger.info("Created Agentuity session %s", session_id)
        return session_id

