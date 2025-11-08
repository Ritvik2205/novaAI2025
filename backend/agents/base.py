"""
Base agent definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.config import Settings
from backend.models.domain import CompanyProfile, LeadProfile
from backend.services.openrouter_client import OpenRouterClient


@dataclass
class AgentContext:
    company: Optional[CompanyProfile] = None
    lead: Optional[LeadProfile] = None
    extras: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company.model_dump(mode="json") if self.company else None,
            "lead": self.lead.model_dump(mode="json") if self.lead else None,
            "extras": self.extras or {},
        }


class BaseAgent:
    """Abstract base class for all agent behaviours."""

    role: str = "assistant"
    name: str = "base-agent"
    purpose: str = "generic"

    def __init__(self, client: OpenRouterClient, settings: Settings):
        self.client = client
        self.settings = settings

    def build_system_prompt(self, context: AgentContext) -> str:
        raise NotImplementedError

    def run(
        self,
        context: AgentContext,
        user_message: str,
        model_override: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Execute the agent using the OpenRouter client."""

        model_cfg = (
            self.settings.high_intent_model if model_override == "high_intent" else self.settings.default_model
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt(context)},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = self.client.chat(
            messages=messages,
            model=model_cfg.name,
            temperature=model_cfg.temperature,
            max_tokens=model_cfg.max_tokens,
            metadata=metadata or {"agent": self.name},
        )
        return response

