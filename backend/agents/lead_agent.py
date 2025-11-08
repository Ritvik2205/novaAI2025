"""
Lead concierge agent responsible for chatting with inbound prospects.
"""

from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List, Optional

from backend.agents.base import AgentContext, BaseAgent


class LeadAgent(BaseAgent):
    name = "lead-concierge"
    purpose = "Handle inbound prospect conversations, qualify, and progress towards scheduling or quoting."

    RESPONSE_PROMPT = textwrap.dedent(
        """
        You are the AI concierge for a contractor CRM. Craft a response for the latest prospect message.
        Requirements:
        - Be warm, professional, and proactive.
        - Use the company voice: helpful, expert, transparent about next steps.
        - Set the tone by explaining you are the company's AI concierge capturing their needs so the most suitable contractor can pick things up smoothly.
        - When applicable, reference retrieved knowledge snippets and confirm project details.
        - Offer scheduling windows when humans are free; if none, offer to provide an instant quote from you.
        - Extract any structured insights (budget, timeline, location, service type).

        Output strictly in JSON with keys:
        - "reply": string to send back to the lead.
        - "lead_updates": object with optional keys (status, preferences, notes) represented as strings.
        - "quote": null or object with keys price (number), currency, scope_summary, delivery_timeline, assumptions (array of strings).
        - "meeting": null or object with keys preferred_start (ISO 8601 string) and duration_minutes (int) if the lead agreed on a time.
        - "follow_up": array of to-do strings for internal agents or humans.
        """
    ).strip()

    def build_system_prompt(self, context: AgentContext) -> str:
        company = context.company
        summary = f"{company.name} specializes in {company.description}" if company and company.description else ""
        return textwrap.dedent(
            f"""
            You are {self.name}, the virtual front-desk agent for {company.name if company else "the company"}.
            {summary}
            Always preserve factual accuracy and politely ask for clarification when unsure.
            Respond in JSON as previously instructed.
            """
        ).strip()

    def _format_history(self, conversation: List[Dict[str, str]]) -> List[Dict[str, str]]:
        history: List[Dict[str, str]] = []
        for message in conversation:
            role = "assistant" if message.get("sender") != "lead" else "user"
            history.append({"role": role, "content": message["content"]})
        return history

    def _format_context_block(
        self,
        rag_context: List[Dict[str, str]],
        availability: Optional[List[Dict[str, str]]],
    ) -> str:
        lines: List[str] = []
        if rag_context:
            lines.append("Retrieved knowledge snippets:")
            for idx, snippet in enumerate(rag_context, start=1):
                excerpt = snippet.get("text", "")[:400]
                source = snippet.get("url") or snippet.get("source", "internal")
                lines.append(f"{idx}. ({source}) {excerpt}")
        if availability:
            lines.append("\nHuman availability windows (ISO start/end):")
            for window in availability:
                lines.append(f"- {window['start']} to {window['end']}")
        return "\n".join(lines)

    def respond_to_lead(
        self,
        context: AgentContext,
        latest_message: str,
        conversation: List[Dict[str, str]],
        rag_context: List[Dict[str, str]],
        availability: Optional[List[Dict[str, str]]] = None,
        require_high_intent: bool = False,
    ) -> Dict[str, Any]:
        context_block = self._format_context_block(rag_context, availability)
        user_prompt = (
            f"{self.RESPONSE_PROMPT}\n\nConversation context provided below for reference.\n"
            f"--- Company & knowledge ---\n{context_block}\n"
            f"--- Latest lead message ---\n{latest_message}"
        )
        history = self._format_history(conversation)
        response = self.run(
            context=context,
            user_message=user_prompt,
            history=history,
            model_override="high_intent" if require_high_intent else None,
        )
        content = response.get("content", "")
        payload = self._parse_json_object(
            content,
            default={
                "reply": "",
                "lead_updates": {},
                "quote": None,
                "meeting": None,
                "follow_up": [],
            },
        )
        if not isinstance(payload.get("follow_up"), list):
            payload["follow_up"] = [str(payload["follow_up"])] if payload.get("follow_up") else []
        return payload

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _strip_code_fence(self, content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                return parts[1 if parts[0] == "" else 2].strip()
        return text

    def _parse_json_object(self, content: str, default: Dict[str, Any]) -> Dict[str, Any]:
        text = self._strip_code_fence(content)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Lead agent returned malformed JSON: {content}")

