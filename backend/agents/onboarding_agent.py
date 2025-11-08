"""
Company onboarding discovery agent.
"""

from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List

from backend.agents.base import AgentContext, BaseAgent


class OnboardingAgent(BaseAgent):
    name = "company-onboarding"
    purpose = "Conduct discovery with company stakeholders to build knowledge graph."

    QUESTION_PROMPT = textwrap.dedent(
        """
        You are configuring an agentic CRM for ScottyLabs, a program that oversees student project teams.
        Craft a numbered JSON array of concise discovery questions that uncover:
        - ScottyLabs' mission, engagement model, and how startups collaborate with student teams.
        - Intake workflow for new partner requests, including vetting criteria and communication cadence.
        - Detailed profiles for each student group: name, focus areas, tools, past work, availability, and point of contact.
        - Project scoping expectations (deliverables, timelines, IP, budget/compensation).
        - Handoff process between AI concierge, student leads, and ScottyLabs mentors.
        - Required documents or knowledge bases (charters, playbooks, onboarding decks).
        - Policies around confidentiality, review checkpoints, and success metrics.

        Constraints:
        - Return ONLY a JSON array of strings (no markdown, no prose). Example: ["Question 1", "..."].
        - Personalize using the supplied company snippet when relevant.
        - Cap at {count} questions.
        """
    ).strip()

    DEFAULT_QUESTION_SET = [
        "Give us ScottyLabs' mission and how you match student teams with external partners.",
        "Describe the end-to-end intake flow when a startup approaches ScottyLabs (steps, owners, timelines).",
        "List each active student group with: name, primary focus areas, notable past projects, and preferred tech/product domains.",
        "For every group, share a point of contact, communication preferences, and current availability windows.",
        "What categories of projects do the groups want more of, and which ones are off-limits?",
        "Outline the milestones you expect during a typical engagement (kickoff, reviews, deliverables, launch).",
        "What resources or documents should partners review (playbooks, code repos, presentation decks)?",
        "How does ScottyLabs evaluate success for a collaboration, and what data should the CRM capture?",
        "Detail how handoffs work between the AI concierge, faculty mentors, and the student team once a lead is qualified.",
        "Are there budget models, IP agreements, or legal requirements partners must accept?",
    ]

    ANSWER_ANALYSIS_PROMPT = textwrap.dedent(
        """
        You are an expert CRM implementation analyst.
        Analyze the stakeholder's answer to the current question. Respond strictly as JSON with keys:
        - "insights": list of short bullet strings capturing facts learnt.
        - "metadata_updates": object of key/value pairs to merge into the company profile (values must be strings).
        - "follow_up_question": null or a concise follow-up question if clarification is needed.
        - "document_requests": list of specific document types to request based on the answer.
        - "tags": list of topical tags to add to the company profile.
        - "group_profiles": array where each item captures a student group with keys:
          name, summary, focus_areas (array), past_projects (array), preferred_tools (array),
          availability, contact_email, metadata (object with any extra notes).
        """
    ).strip()

    def build_system_prompt(self, context: AgentContext) -> str:
        company_desc = context.company.description if context.company else "Unknown company"
        return textwrap.dedent(
            f"""
            You are {self.name}, an onboarding specialist configuring an agentic CRM.
            Company context: {company_desc}
            When responding, follow instructions exactly and output valid JSON.
            """
        ).strip()

    def generate_questionnaire(self, company_snippet: str, count: int = 7) -> List[str]:
        prompt = self.QUESTION_PROMPT.format(count=count) + f"\nCompany snippet: {company_snippet}"
        response = self.run(AgentContext(), prompt)
        content = response.get("content", "")
        questions = self._parse_json_array(content)
        lowered_snippet = company_snippet.lower()
        if "scotty" in lowered_snippet or "student" in lowered_snippet:
            return self.DEFAULT_QUESTION_SET[:count]
        if not questions:
            return self.DEFAULT_QUESTION_SET[:count]
        return questions

    def analyze_answer(
        self,
        context: AgentContext,
        question: str,
        answer: str,
    ) -> Dict[str, Any]:
        user_prompt = (
            f"{self.ANSWER_ANALYSIS_PROMPT}\n\nCurrent question: {question}\nStakeholder answer: {answer}"
        )
        response = self.run(context, user_prompt)
        content = response.get("content", "")
        return self._parse_json_object(
            content,
            default={
                "insights": [],
                "metadata_updates": {},
                "follow_up_question": None,
                "document_requests": [],
                "tags": [],
                "group_profiles": [],
            },
        )

    def summarize_session(
        self,
        context: AgentContext,
        qa_pairs: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        summary_prompt = textwrap.dedent(
            """
            Compile a concise operating profile for the company from the provided Q/A pairs.
            Respond in JSON with keys:
            - "profile": paragraph summarizing services, positioning, target clients, regions.
            - "recommendations": array of setup actions for the CRM (automations, data to import, integrations).
            - "key_contacts": array of objects with keys name, role, email (if available).
            - "student_groups_overview": array of short blurbs summarizing each group and how they engage.
            - "data_gaps": array of questions that still need answers.
            """
        ).strip()
        qa_json = json.dumps(qa_pairs, ensure_ascii=False)
        response = self.run(
            context,
            user_message=f"{summary_prompt}\n\nQ/A data: {qa_json}",
            model_override="high_intent",
        )
        content = response.get("content", "")
        return self._parse_json_object(
            content,
            default={
                "profile": "",
                "recommendations": [],
                "key_contacts": [],
                "student_groups_overview": [],
                "data_gaps": [],
            },
        )

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
        return default

    def _parse_json_array(self, content: str) -> List[str]:
        text = self._strip_code_fence(content)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                pass
        return []

