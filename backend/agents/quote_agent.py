"""
Pricing and proposal generation agent.
"""

from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List

from backend.agents.base import AgentContext, BaseAgent


class QuoteAgent(BaseAgent):
    name = "quote-strategist"
    purpose = "Synthesize quotes and proposal outlines when humans are unavailable."

    QUOTE_PROMPT = textwrap.dedent(
        """
        You are generating a quote for a prospective client based on the gathered context.
        Build a reasonable price, delivery timeline, and assumptions.
        Return JSON with keys:
        - "price": number (default currency USD)
        - "currency": string
        - "scope_summary": short paragraph
        - "delivery_timeline": human readable string
        - "assumptions": array of bullet strings
        - "confidence": "low" | "medium" | "high"
        """
    ).strip()

    def build_system_prompt(self, context: AgentContext) -> str:
        company = context.company
        company_line = f"{company.name} specializes in {company.description}" if company else "Company details pending."
        return textwrap.dedent(
            f"""
            You are {self.name}, responsible for rapid-yet-grounded quotes on behalf of the company.
            {company_line}
            Always err on transparency about assumptions and mention when human verification is recommended.
            Output strictly as JSON as instructed.
            """
        ).strip()

    def generate_quote(
        self,
        context: AgentContext,
        opportunity_summary: str,
        rag_context: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        knowledge = "\n".join(f"- {chunk.get('text', '')[:300]}" for chunk in rag_context)
        user_prompt = f"{self.QUOTE_PROMPT}\n\nOpportunity summary:\n{opportunity_summary}\n\nKnowledge context:\n{knowledge}"
        response = self.run(context=context, user_message=user_prompt, model_override="high_intent")
        content = response.get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Quote agent returned malformed JSON: {content}") from exc

