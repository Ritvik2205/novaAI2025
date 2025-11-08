"""
Conversation monitoring agent that extracts structured action items.
"""

from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List

from backend.agents.base import AgentContext, BaseAgent


class ActionMonitorAgent(BaseAgent):
    name = "conversation-analyst"
    purpose = "Track lead conversations, highlight commitments, and surface next actions."

    MONITOR_PROMPT = textwrap.dedent(
        """
        You watch a conversation between a prospective client and the company's virtual agents or humans.
        Extract operational details to keep the CRM up-to-date.

        Respond strictly as JSON with the following shape:
        {
          "summary": "One paragraph recap of the latest conversation turn.",
          "action_items": ["short imperative bullet points..."],
          "lead_updates": {
            "status": "<optional new lifecycle status>",
            "preferences": { "key": "value" },
            "notes": ["additional notes to append"]
          },
          "assignment": {
            "contractor": "Name or team best suited",
            "reason": "Why they were chosen"
          },
          "schedule": {
            "should_schedule": true | false,
            "preferred_start": "ISO-8601" | null,
            "duration_minutes": 30,
            "assignees": ["contractor type or owner"],
            "fallback_to_agent": true | false
          },
          "quote": {
            "price": 0,
            "currency": "USD",
            "scope_summary": "...",
            "delivery_timeline": "...",
            "assumptions": ["..."]
          }
        }

        Omit optional fields or set them to null when you lack the information.
        Never include commentary outside of JSON.
        """
    ).strip()

    def build_system_prompt(self, context: AgentContext) -> str:
        company_line = (
            f"You are monitoring conversations for {context.company.name}."
            if context.company
            else "You are monitoring conversations for the contractor CRM."
        )
        return textwrap.dedent(
            f"""
            You are {self.name}, a compliance and operations analyst.
            {company_line}
            Stay factual, avoid hallucinations, and only output JSON as instructed.
            """
        ).strip()

    def observe_conversation(
        self,
        context: AgentContext,
        conversation: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        transcript = [
            {"sender": entry.get("sender", ""), "content": entry.get("content", "")}
            for entry in conversation
        ]
        user_prompt = f"{self.MONITOR_PROMPT}\n\nConversation transcript:\n{json.dumps(transcript, ensure_ascii=False)}"
        response = self.run(context=context, user_message=user_prompt, model_override="high_intent")
        content = response.get("content", "")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Action monitor returned invalid JSON: {content}") from exc
        return payload

