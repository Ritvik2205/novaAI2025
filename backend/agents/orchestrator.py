"""
High level orchestration for the agentic CRM system.
"""

from __future__ import annotations

import base64
import csv
import json
import logging
import mimetypes
import threading
import uuid
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.utils import secure_filename

from backend.agents.base import AgentContext
from backend.agents.action_monitor_agent import ActionMonitorAgent
from backend.agents.lead_agent import LeadAgent
from backend.agents.onboarding_agent import OnboardingAgent
from backend.agents.quote_agent import QuoteAgent
from backend.config import Settings
from backend.models.domain import CompanyProfile, LeadProfile, Meeting, Quote, StudentGroup
from backend.repositories.memory import CRMRepository
from backend.services.agentuity_client import AgentuityClient
from backend.services.openrouter_client import OpenRouterClient
from backend.services.rag_service import DocumentPayload, RAGService
from backend.services.scheduler import CalendarService


logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates agents, repositories, and integrations."""

    def __init__(
        self,
        repository: CRMRepository,
        openrouter: OpenRouterClient,
        agentuity: AgentuityClient,
        calendar: CalendarService,
        rag: RAGService,
        settings: Settings,
    ):
        self.repository = repository
        self.openrouter = openrouter
        self.agentuity = agentuity
        self.calendar = calendar
        self.rag = rag
        self.settings = settings

        self.onboarding_agent = OnboardingAgent(openrouter, settings)
        self.lead_agent = LeadAgent(openrouter, settings)
        self.quote_agent = QuoteAgent(openrouter, settings)
        self.monitor_agent = ActionMonitorAgent(openrouter, settings)

        self._agentuity_catalog: Dict[str, Optional[str]] = {}
        self._publish_agentuity_catalog()
        self._ensure_default_company()

    # ------------------------------------------------------------------
    # Agent catalog
    # ------------------------------------------------------------------
    def _publish_agentuity_catalog(self) -> None:
        """Push agent definitions to Agentuity if configured."""

        for agent in [self.onboarding_agent, self.lead_agent, self.quote_agent, self.monitor_agent]:
            definition = {
                "name": agent.name,
                "description": agent.purpose,
                "system_prompt": agent.build_system_prompt(AgentContext()),
            }
            agent_id = self.agentuity.sync_agent(definition)
            self._agentuity_catalog[agent.name] = agent_id

    # ------------------------------------------------------------------
    # Company onboarding
    # ------------------------------------------------------------------
    def start_onboarding(self, payload: Dict[str, str]) -> Dict[str, Any]:
        name = payload["name"]
        description = payload.get("description")
        website = payload.get("website")
        target_company_id = payload.get("company_id")

        company: CompanyProfile
        if target_company_id:
            company = self.repository.get_company(target_company_id)
            if not company:
                raise KeyError(f"Company {target_company_id} not found.")
            if description:
                company.description = description
            if website:
                company.website = website
            self.repository.update_company(company)
        else:
            existing = self.repository.list_companies()
            matched = next((c for c in existing if c.name.lower() == name.lower()), None)
            if matched:
                company = matched
                if description:
                    company.description = description
                if website:
                    company.website = website
                self.repository.update_company(company)
            else:
                company = self.repository.create_company(name=name, website=website, description=description)

        mission = company.metadata.get("mission") or payload.get("mission") or ""
        snippet = (
            f"Name: {company.name}\nWebsite: {company.website}\nDescription: {company.description}\nMission: {mission}"
        )
        questions = self.onboarding_agent.generate_questionnaire(snippet)
        session = self.repository.create_onboarding_session(company_id=company.id, questions=questions)

        if website:
            threading.Thread(target=self._crawl_site, args=(company.id, website), daemon=True).start()

        return {
            "company": company.model_dump(mode="json"),
            "session_id": session.session_id,
            "next_question": session.next_question,
        }

    def answer_onboarding(self, session_id: str, answer: str) -> Dict[str, Any]:
        session = self.repository.get_onboarding_session(session_id)
        if not session:
            raise KeyError(f"Onboarding session {session_id} not found.")

        company = self.repository.get_company(session.company_id)
        if not company:
            raise KeyError(f"Company {session.company_id} not found.")

        question = session.next_question
        if not question:
            return {"status": "completed"}

        context = AgentContext(company=company)
        analysis = self.onboarding_agent.analyze_answer(context, question, answer)

        session.answers.append(answer)
        if len(session.answers) >= len(session.questions):
            session.status = "completed"
        self.repository.save_onboarding_session(session)

        if analysis.get("metadata_updates"):
            flattened = {k: str(v) for k, v in analysis["metadata_updates"].items()}
            company = self.repository.add_company_metadata(company.id, flattened)

        group_profiles = analysis.get("group_profiles") or []
        if group_profiles:
            created_groups: List[Dict[str, Any]] = []
            for entry in group_profiles:
                if isinstance(entry, str):
                    try:
                        entry = json.loads(entry)
                    except json.JSONDecodeError:
                        continue
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if not name:
                    continue
                data = {
                    "summary": entry.get("summary"),
                    "focus_areas": entry.get("focus_areas", []),
                    "past_projects": entry.get("past_projects", []),
                    "preferred_tools": entry.get("preferred_tools", []),
                    "contact_email": entry.get("contact_email"),
                    "availability": entry.get("availability"),
                    "metadata": entry.get("metadata") or {},
                }
                group = self.repository.upsert_student_group(company.id, name=name, data=data)
                created_groups.append(group.model_dump(mode="json"))
        if created_groups:
            company.student_groups = created_groups

        if analysis.get("tags"):
            tags = set(company.tags)
            tags.update(analysis["tags"])
            company.tags = list(tags)
            self.repository.update_company(company)

        insights = analysis.get("insights", [])
        if insights:
            existing = json.loads(company.metadata.get("insights", "[]"))
            existing.extend(insights)
            self.repository.add_company_metadata(company.id, {"insights": json.dumps(existing)})

        next_question = analysis.get("follow_up_question") or session.next_question
        doc_requests = analysis.get("document_requests", [])

        payload = {
            "status": session.status,
            "insights": insights,
            "document_requests": doc_requests,
            "next_question": next_question,
        }

        if session.status == "completed":
            qa_pairs = [{"question": q, "answer": a} for q, a in zip(session.questions, session.answers)]
            summary = self.onboarding_agent.summarize_session(context, qa_pairs)
            payload["summary"] = summary

        return payload

    # ------------------------------------------------------------------
    # Knowledge ingestion
    # ------------------------------------------------------------------
    def ingest_uploaded_files(self, company_id: str, files: List) -> Dict[str, Any]:
        company = self.repository.get_company(company_id)
        if not company:
            raise KeyError(f"Company {company_id} not found.")

        upload_dir = Path(self.settings.uploads_dir) / company_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        payloads: List[DocumentPayload] = []
        stored_files: List[str] = []

        for uploaded in files:
            filename = secure_filename(uploaded.filename)
            if not filename:
                continue
            path = upload_dir / filename
            uploaded.save(path)
            text = self._extract_text_from_file(path)
            if not text:
                continue
            doc_id = uuid.uuid4().hex
            payloads.append(
                DocumentPayload(
                    doc_id=doc_id,
                    text=text,
                    metadata={
                        "source": "document",
                        "filename": filename,
                    },
                )
            )
            stored_files.append(str(path))
            self.repository.attach_document(company_id, str(path))

        chunk_count = self.rag.ingest_documents(company_id, payloads)
        return {"ingested_documents": len(payloads), "chunks": chunk_count, "stored_files": stored_files}

    def ingest_urls(self, company_id: str, urls: List[str]) -> Dict[str, int]:
        return self.rag.ingest_urls(company_id, urls)

    def _crawl_site(self, company_id: str, base_url: str) -> None:
        logger.info("Starting background crawl for company %s", company_id)
        try:
            result = self.rag.ingest_urls(company_id, [base_url])
            metadata = {
                "last_crawl_pages": str(result.get("pages", 0)),
                "last_crawl_chunks": str(result.get("chunks", 0)),
                "last_crawl_at": datetime.utcnow().isoformat(),
            }
            self.repository.add_company_metadata(company_id, metadata)
        except Exception as exc:
            logger.exception("Background crawl failed for %s: %s", company_id, exc)
            self.repository.add_company_metadata(
                company_id,
                {
                    "last_crawl_error": str(exc),
                    "last_crawl_at": datetime.utcnow().isoformat(),
                },
            )

    def query_knowledge(self, company_id: str, question: str) -> Dict[str, Any]:
        context = self.rag.query(company_id, question)
        return context

    def list_company_documents(self, company_id: str) -> List[Dict[str, str]]:
        company = self.repository.get_company(company_id)
        if not company:
            raise KeyError(f"Company {company_id} not found.")
        documents = self.repository.list_company_documents(company_id)
        return [{"path": path, "name": Path(path).name} for path in documents]

    def generate_knowledge_sections(self, company_id: str) -> Dict[str, Any]:
        company = self.repository.get_company(company_id)
        if not company:
            raise KeyError(f"Company {company_id} not found.")
        groups = self.repository.list_student_groups(company_id)
        documents = self.repository.list_company_documents(company_id)

        insights_raw = company.metadata.get("insights")
        if insights_raw:
            try:
                insights = json.loads(insights_raw)
            except json.JSONDecodeError:
                insights = [insights_raw]
        else:
            insights = []

        visibility_raw = company.metadata.get("knowledge_visibility")
        internal_only: List[str] = []
        if visibility_raw:
            try:
                data = json.loads(visibility_raw)
                internal_only = data.get("internal_only", [])
            except json.JSONDecodeError:
                internal_only = []

        rag_context = self.rag.query(company_id, "Summarize key knowledge about ScottyLabs collaborations")["context"]

        context_payload = {
            "company": company.model_dump(mode="json"),
            "insights": insights,
            "student_groups": [group.model_dump(mode="json") for group in groups],
            "documents": documents,
            "rag_context": rag_context,
        }

        system_prompt = (
            "You are a knowledge architect organizing ScottyLabs' onboarding information into reusable sections. "
            "Produce concise, factual summaries suitable for sharing with client partners or retaining as internal context."
        )
        user_prompt = (
            "Using the structured context below, create between 4 and 8 sections that capture the company's knowledge. "
            "Each section must include:\n"
            '- "title": short heading,\n'
            '- "summary": 2-3 sentence overview,\n'
            '- "key_points": bullet list of specifics (array of strings),\n'
            '- "recommended_audience": one of ["client","internal","both"] depending on sensitivity,\n'
            '- Optional "notes" array for follow-ups.\n'
            "Respond ONLY with JSON object: {\"sections\": [...]}.\n"
            f"Context:\n{json.dumps(context_payload, ensure_ascii=False)}"
        )

        completion = self.openrouter.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=self.settings.high_intent_model.name,
            temperature=0.2,
            max_tokens=self.settings.high_intent_model.max_tokens,
            metadata={"agent": "knowledge-architect"},
        )
        parsed = self._parse_json_payload(completion.get("content", ""))
        sections = parsed.get("sections") or []

        normalized: List[Dict[str, Any]] = []
        internal_only_set = {title.lower() for title in internal_only}
        for section in sections:
            if isinstance(section, str):
                try:
                    section = json.loads(section)
                except json.JSONDecodeError:
                    continue
            if not isinstance(section, dict):
                continue
            title = section.get("title") or "Untitled Section"
            summary = section.get("summary") or ""
            key_points = section.get("key_points") or []
            recommended = (section.get("recommended_audience") or "both").lower()
            share = section.get("share_with_clients")
            if share is None:
                share = recommended in {"client", "both"}
            share = bool(share) and title.lower() not in internal_only_set
            normalized.append(
                {
                    "title": title,
                    "summary": summary,
                    "key_points": [str(point) for point in key_points],
                    "recommended_audience": recommended,
                    "share_with_clients": share,
                }
            )
        return {"sections": normalized, "internal_only": internal_only}

    def update_knowledge_visibility(self, company_id: str, internal_only: List[str]) -> Dict[str, Any]:
        company = self.repository.get_company(company_id)
        if not company:
            raise KeyError(f"Company {company_id} not found.")
        payload = json.dumps({"internal_only": internal_only})
        self.repository.add_company_metadata(company_id, {"knowledge_visibility": payload})
        return {"internal_only": internal_only}

    def list_student_groups(self, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if company_id and not self.repository.get_company(company_id):
            raise KeyError(f"Company {company_id} not found.")
        groups = self.repository.list_student_groups(company_id)
        return [group.model_dump(mode="json") for group in groups]

    def _select_company_for_lead(self, payload: Dict[str, Any]) -> CompanyProfile:
        company_id = payload.get("company_id")
        if company_id:
            company = self.repository.get_company(company_id)
            if company:
                return company
        companies = self.repository.list_companies()
        if not companies:
            raise ValueError("No companies configured. Complete onboarding first.")
        # Simple heuristic: choose the first company. Could be extended with domain matching later.
        return companies[0]

    def answer_company_question(self, company_id: str, question: str) -> Dict[str, Any]:
        company = self.repository.get_company(company_id)
        if not company:
            raise KeyError(f"Company {company_id} not found.")
        rag_result = self.rag.query(company_id, question)
        context_chunks = rag_result.get("context", [])
        context_text = "\n".join(chunk.get("text", "") for chunk in context_chunks)
        system_prompt = (
            f"You are the knowledge assistant for {company.name if company else 'the company'}."
            " Answer questions factually using the provided context. If unsure, state that clearly."
        )
        user_message = f"Question: {question}\n\nContext:\n{context_text or 'No context available.'}"
        completion = self.openrouter.chat(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            model=self.settings.default_model.name,
            temperature=self.settings.default_model.temperature,
            max_tokens=self.settings.default_model.max_tokens,
            metadata={"agent": "knowledge-assistant"},
        )
        return {"answer": completion.get("content", ""), "context": context_chunks}

    # ------------------------------------------------------------------
    # Lead management
    # ------------------------------------------------------------------
    def handle_inbound_message(self, payload: Dict[str, str]) -> Dict[str, Any]:
        company = self._select_company_for_lead(payload)
        company_id = company.id

        lead_id = payload.get("lead_id")
        lead = self.repository.get_lead(lead_id) if lead_id else None

        if not lead:
            lead = self.repository.create_lead(
                company_id=company_id,
                name=payload.get("name"),
                email=payload.get("email"),
                phone=payload.get("phone"),
                initial_notes=payload.get("message"),
            )
        lead_id = lead.id

        client_code = lead.metadata.get("client_code")
        if not client_code:
            client_code = f"SCOT-{uuid.uuid4().hex[:4].upper()}"
            lead.metadata["client_code"] = client_code

        incoming_message = payload["message"]
        self.repository.add_message(lead_id=lead_id, sender="lead", content=incoming_message)

        conversation = [
            {"sender": msg.sender, "content": msg.content} for msg in self.repository.get_messages(lead_id)
        ]

        rag_context = self.rag.query(company_id, incoming_message).get("context", [])
        availability = self.calendar.get_availability(company_id)

        agent_response = self.lead_agent.respond_to_lead(
            context=AgentContext(company=company, lead=lead),
            latest_message=incoming_message,
            conversation=conversation,
            rag_context=rag_context,
            availability=availability,
            require_high_intent=payload.get("priority") == "high",
        )

        reply_text = agent_response.get("reply", "")
        if client_code and lead.metadata.get("code_shared") != "yes":
            appendix = f"Here is your project reference code: {client_code}. Please keep it handy for future conversations."
            reply_text = (reply_text + "\n\n" + appendix).strip()
            lead.metadata["code_shared"] = "yes"
        if reply_text:
            self.repository.add_message(lead_id=lead_id, sender="agent", content=reply_text)

        conversation = [
            {"sender": msg.sender, "content": msg.content} for msg in self.repository.get_messages(lead_id)
        ]

        updates = agent_response.get("lead_updates") or {}
        if updates.get("status"):
            lead.status = updates["status"]
        preferences_update = updates.get("preferences")
        if preferences_update:
            self._merge_preferences(lead.preferences, preferences_update)
        notes_update = updates.get("notes")
        if notes_update:
            if isinstance(notes_update, list):
                lead.notes.extend(str(item) for item in notes_update)
            else:
                lead.notes.append(str(notes_update))

        quote_payload: Optional[Quote] = None
        if agent_response.get("quote"):
            quote_info = agent_response["quote"]
            quote_payload = self._persist_quote(company_id, lead, quote_info)

        meeting_payload: Optional[Meeting] = None
        if agent_response.get("meeting"):
            meeting_info = agent_response["meeting"]
            meeting_payload = self._schedule_meeting(company, lead, meeting_info)

        monitor_summary: Dict[str, Any] = {}
        try:
            monitor_summary = self.monitor_agent.observe_conversation(
                context=AgentContext(company=company, lead=lead),
                conversation=conversation,
            )
        except ValueError as exc:
            logger.warning("Monitor agent failed for lead %s: %s", lead_id, exc)
            monitor_summary = {}

        if monitor_summary:
            lead_updates = monitor_summary.get("lead_updates") or {}
            if lead_updates.get("status"):
                lead.status = lead_updates["status"]
                if str(lead.status).lower() in {"won", "contracted", "signed"}:
                    lead.metadata["quote_acceptance"] = "yes"
            preferences_update = lead_updates.get("preferences")
            if preferences_update:
                self._merge_preferences(lead.preferences, preferences_update)
            notes = lead_updates.get("notes")
            if notes:
                if isinstance(notes, list):
                    lead.notes.extend(str(item) for item in notes)
                else:
                    lead.notes.append(str(notes))

            for item in monitor_summary.get("action_items", []) or []:
                cleaned = str(item).strip()
                if cleaned and cleaned not in lead.action_items:
                    lead.action_items.append(cleaned)

            summary_text = monitor_summary.get("summary")
            if summary_text:
                lead.metadata["last_summary"] = str(summary_text)

            assignment = monitor_summary.get("assignment") or {}
            contractor = assignment.get("contractor")
            if contractor:
                lead.metadata["assigned_contractor"] = str(contractor)
                reason = assignment.get("reason")
                if reason:
                    lead.metadata["assignment_reason"] = str(reason)

            schedule_data = monitor_summary.get("schedule") or {}
            if (
                schedule_data
                and schedule_data.get("should_schedule")
                and schedule_data.get("preferred_start")
            ):
                schedule_payload = {
                    "preferred_start": schedule_data.get("preferred_start"),
                    "duration_minutes": schedule_data.get("duration_minutes", 30),
                }
                try:
                    meeting_payload = meeting_payload or self._schedule_meeting(
                        company, lead, schedule_payload
                    )
                except Exception as exc:  # pragma: no cover - scheduling fallback
                    logger.warning("Automated scheduling failed for lead %s: %s", lead_id, exc)

            quote_info = monitor_summary.get("quote") or {}
            if not quote_payload and quote_info.get("price"):
                quote_payload = self._persist_quote(company_id, lead, quote_info)
            if quote_info:
                status_token = str(quote_info.get("status", "")).lower()
                accepted_flag = quote_info.get("accepted")
                if (
                    accepted_flag is True
                    or status_token in {"accepted", "approved", "agreed"}
                    or str(quote_info.get("decision", "")).lower() in {"accept", "accepted"}
                ):
                    lead.metadata["quote_acceptance"] = "yes"

            lead.metadata["monitor_snapshot"] = json.dumps(monitor_summary)

        accepted = self._is_quote_accepted(lead)
        if self._message_signals_acceptance(incoming_message):
            accepted = True
            lead.metadata["quote_acceptance"] = "yes"

        recommendations: List[StudentGroup] = []
        if accepted and (quote_payload or lead.quoted_price is not None):
            recommendations = self._recommend_student_groups(
                company_id=company_id,
                lead=lead,
                latest_message=incoming_message,
                rag_context=rag_context,
            )
            recommendations = self._ensure_signature_groups(company_id, recommendations)

        self.repository.update_lead(lead)

        return {
            "reply": reply_text,
            "lead": lead.model_dump(mode="json"),
            "quote": quote_payload.model_dump(mode="json") if quote_payload else None,
            "meeting": meeting_payload.model_dump(mode="json") if meeting_payload else None,
            "follow_up": agent_response.get("follow_up", []),
            "rag_context": rag_context,
            "monitor_summary": monitor_summary,
            "recommendations": [
                {
                    "id": group.id,
                    "name": group.name,
                    "summary": group.summary,
                    "focus_areas": group.focus_areas,
                    "profile_image_url": group.profile_image_url,
                    "hire_rate": group.metadata.get("hire_rate"),
                }
                for group in recommendations
            ],
            "client_code": client_code,
        }

    def list_leads(self, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        leads = self.repository.list_leads(company_id)
        return [lead.model_dump(mode="json") for lead in leads]

    def get_lead(self, lead_id: str) -> Dict[str, Any]:
        lead = self.repository.get_lead(lead_id)
        if not lead:
            raise KeyError(f"Lead {lead_id} not found.")
        messages = [message.model_dump(mode="json") for message in self.repository.get_messages(lead_id)]
        quotes = [quote.model_dump(mode="json") for quote in self.repository.list_quotes(lead_id)]
        monitor_summary = None
        snapshot = lead.metadata.get("monitor_snapshot")
        if snapshot:
            try:
                monitor_summary = json.loads(snapshot)
            except json.JSONDecodeError:
                monitor_summary = None
        return {
            "lead": lead.model_dump(mode="json"),
            "messages": messages,
            "quotes": quotes,
            "monitor_summary": monitor_summary,
        }

    def handoff_lead(self, lead_id: str, group_id: Optional[str], decision: str) -> Dict[str, Any]:
        lead = self.repository.get_lead(lead_id)
        if not lead:
            raise KeyError(f"Lead {lead_id} not found.")
        decision_normalized = (decision or "").lower()
        if decision_normalized not in {"send", "decline"}:
            raise ValueError("decision must be 'send' or 'decline'")

        selected_group = None
        if decision_normalized == "send":
            if not group_id:
                raise ValueError("group_id is required when decision is 'send'")
            group_lookup = {group.id: group for group in self.repository.list_student_groups(lead.company_id)}
            selected_group = group_lookup.get(group_id)
            if not selected_group:
                raise KeyError(f"Student group {group_id} not found.")

        self.repository.record_lead_handoff(
            lead_id=lead_id,
            group_id=group_id if decision_normalized == "send" else None,
            decision=decision_normalized,
        )

        if decision_normalized == "send":
            lead.status = "qualified"
            if selected_group:
                lead.metadata["assigned_contractor"] = selected_group.name
                lead.metadata["assignment_reason"] = "Client selected group via portal"
        else:
            lead.metadata["assignment_reason"] = "Client opted out of sharing information"

        self.repository.update_lead(lead)
        return {
            "lead": lead.model_dump(mode="json"),
            "decision": decision_normalized,
            "group_id": group_id,
        }

    def _recommend_student_groups(
        self,
        company_id: str,
        lead: LeadProfile,
        latest_message: str,
        rag_context: List[Dict[str, Any]],
    ) -> List[StudentGroup]:
        groups = self.repository.list_student_groups(company_id)
        if not groups:
            return []

        keywords = self._extract_keywords(latest_message)
        for value in lead.preferences.values():
            keywords |= self._extract_keywords(value)
        for note in lead.notes:
            keywords |= self._extract_keywords(note)
        for ctx in rag_context:
            keywords |= self._extract_keywords(ctx.get("text", ""))

        scored: List[tuple[int, StudentGroup]] = []
        for group in groups:
            tokens: set[str] = set()
            for focus in group.focus_areas:
                tokens |= self._extract_keywords(focus)
            if group.summary:
                tokens |= self._extract_keywords(group.summary)
            score = len(tokens & keywords)
            scored.append((score, group))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = [group for score, group in scored if score > 0][:3]
        if not top:
            top = [group for _, group in scored[:3]]
        return top

    def _extract_keywords(self, text: str) -> set[str]:
        if not text:
            return set()
        return {token for token in re.findall(r"[a-zA-Z]+", text.lower()) if len(token) > 2}

    def _ensure_signature_groups(
        self, company_id: str, current: List[StudentGroup]
    ) -> List[StudentGroup]:
        groups = self.repository.list_student_groups(company_id)
        if not groups:
            return current
        name_map = {group.name.lower(): group for group in groups}

        signature_names = [
            "jake paul",
            "thomas kanz",
        ]
        ordered: List[StudentGroup] = []
        seen: set[str] = set()

        for signature in signature_names:
            match = name_map.get(signature)
            if match:
                ordered.append(match)
                seen.add(match.id)

        for group in current:
            if group.id not in seen:
                ordered.append(group)
                seen.add(group.id)

        return ordered[:3]

    def _merge_preferences(self, current: Dict[str, str], updates: Any) -> None:
        if isinstance(updates, dict):
            for key, value in updates.items():
                current[str(key)] = str(value)
        elif isinstance(updates, list):
            for idx, item in enumerate(updates, start=1):
                current[f"pref_{idx}"] = str(item)
        else:
            current["summary"] = str(updates)

    def _is_quote_accepted(self, lead: LeadProfile) -> bool:
        if lead.metadata.get("quote_acceptance") == "yes":
            return True
        status = (lead.status or "").lower()
        if status in {"won", "contracted", "signed"}:
            return True
        decision = (lead.metadata.get("handoff_decision") or "").lower()
        if decision == "send":
            return True
        return False

    def _message_signals_acceptance(self, latest_message: str) -> bool:
        message = (latest_message or "").lower()
        acceptance_keywords = [
            "we agree",
            "sounds good",
            "let's proceed",
            "let us proceed",
            "accept the quote",
            "approved",
            "let's do it",
            "we accept",
            "go ahead",
            "proceed",
            "yes please",
            "looks good",
            "works for me",
            "that works",
            "i accept",
            "i agree",
            "deal",
            "lock it in",
            "let's move forward",
        ]
        return any(keyword in message for keyword in acceptance_keywords)

    def _ensure_default_company(self) -> None:
        existing = self.repository.list_companies()
        if existing:
            self._seed_student_groups(existing[0].id)
            return
        profile = self.repository.create_company(
            name="ScottyLabs",
            website="https://scottylabs.org",
            description="ScottyLabs coordinates student-led innovation teams to collaborate with industry partners.",
        )
        self.repository.add_company_metadata(
            profile.id,
            {
                "mission": "Empower student builders to deliver high-quality technology and product prototypes for real stakeholders.",
                "engagement_model": "Partners submit project briefs; ScottyLabs matches the best student group and mentors delivery.",
            },
        )
        self._seed_student_groups(profile.id)

    def _seed_student_groups(self, company_id: str) -> None:
        existing_groups = self.repository.list_student_groups(company_id)
        if existing_groups:
            has_jake = any(group.name.lower().startswith("jake paul") for group in existing_groups)
            if has_jake and len(existing_groups) >= 21 and all(
                group.profile_image_url and group.profile_image_url.startswith("data:") for group in existing_groups
            ):
                return
            self.repository.remove_student_groups(company_id)
        base_dir = Path(__file__).resolve().parents[2]
        people_dir = base_dir / "frontend" / "dist" / "assets" / "people"
        if not people_dir.exists():
            legacy_dir = base_dir / "People"
            if legacy_dir.exists():
                people_dir = legacy_dir
        csv_path = people_dir / "sample_staff.csv"
        if not csv_path.exists():
            logger.warning("sample_staff.csv not found; skipping student group seeding.")
            return

        with csv_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        if not rows:
            return

        # Ensure a dedicated 21st Jake Paul group exists
        if len(rows) < 21:
            logger.warning("sample_staff.csv contains fewer than 21 rows; expected at least 21 entries.")
        jake_prototype = dict(rows[0])
        extra_jake = {
            "name": f"{jake_prototype.get('name', 'Jake Paul').strip()} Collective",
            "specialty": jake_prototype.get("specialty", "Treehouse Architecture"),
            "pros": jake_prototype.get("pros", "Signature elevated living spaces"),
            "cons": jake_prototype.get("cons", "prefers premium materials"),
            "wage": jake_prototype.get("wage", "100"),
            "location": jake_prototype.get("location", "local"),
        }
        rows.insert(0, extra_jake)

        image_order: List[Optional[Path]] = []
        primary = people_dir / "jakePaul.png"
        image_order.append(primary if primary.exists() else None)
        for idx in range(1, len(rows)):
            matched: Optional[Path] = None
            for suffix in (".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG", ".webp", ".WEBP"):
                candidate = people_dir / f"person_{idx}{suffix}"
                if candidate.exists():
                    matched = candidate
                    break
            image_order.append(matched)
        if rows and primary.exists():
            image_order[0] = primary
            if len(image_order) > 1:
                image_order[1] = primary

        for index, row in enumerate(rows):
            name = row.get("name", "Unnamed Group").strip()
            specialty = (row.get("specialty") or "").strip()
            pros = (row.get("pros") or "").strip()
            cons = (row.get("cons") or "").strip()
            wage = (row.get("wage") or "").strip()
            location = (row.get("location") or "").strip()

            summary_parts = []
            if specialty:
                summary_parts.append(f"{specialty} specialists.")
            if pros:
                summary_parts.append(f"Strengths: {pros}.")
            if cons:
                summary_parts.append(f"Watch-outs: {cons}.")
            summary = " ".join(summary_parts) or "ScottyLabs project team."

            focus_areas = [token for token in {specialty, pros} if token]
            past_projects = [f"Recent highlight: {pros}"] if pros else []
            preferred_tools = [specialty] if specialty else []

            email_slug = name.lower().replace(" ", ".")
            email = f"{email_slug}@scottylabs.org"

            availability = "Remote (IST overlap)" if "india" in location.lower() else "Local availability"

            hire_rate = wage
            if hire_rate and hire_rate.isdigit():
                hire_rate = f"${hire_rate}/hr"

            image_data = None
            image_path = image_order[index] if index < len(image_order) else None
            if image_path and image_path.exists():
                try:
                    content = image_path.read_bytes()
                    encoded = base64.b64encode(content).decode("utf-8")
                    suffix = image_path.suffix.lower()
                    mime = "image/png" if suffix == ".png" else "image/jpeg"
                    image_data = f"data:{mime};base64,{encoded}"
                except Exception as exc:  # pragma: no cover - non-critical
                    logger.warning("Failed encoding profile image %s: %s", image_path, exc)

            self.repository.create_student_group(
                company_id,
                name=name,
                summary=summary,
                focus_areas=focus_areas if focus_areas else ([specialty] if specialty else []),
                past_projects=past_projects,
                preferred_tools=preferred_tools,
                contact_email=email,
                availability=availability,
                profile_image_url=image_data,
                metadata={
                    "hire_rate": hire_rate or "Negotiable",
                    "cons": cons,
                    "location": location,
                },
            )

    def _parse_json_payload(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1 if parts[0] == "" else 2].strip()
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
        return {}

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def set_availability(self, company_id: str, windows: List[Dict[str, str]]) -> None:
        self.calendar.set_availability(company_id, windows)

    def _schedule_meeting(self, company: CompanyProfile, lead: LeadProfile, data: Dict[str, Any]) -> Meeting:
        start_iso = data.get("preferred_start")
        if not start_iso:
            raise ValueError("Meeting payload missing preferred_start")
        start_time = datetime.fromisoformat(start_iso)
        duration_minutes = data.get("duration_minutes", 30)
        end_time = start_time + timedelta(minutes=duration_minutes)

        event = self.calendar.schedule_event(
            company_id=company.id,
            lead_name=lead.name or "Prospect",
            attendees=[email for email in [lead.email, company.metadata.get("primary_contact_email")] if email],
            start_time=start_time,
            end_time=end_time,
            title=f"Discovery call with {lead.name or 'prospect'}",
        )

        meeting = Meeting(
            id=uuid.uuid4().hex,
            lead_id=lead.id,
            company_id=company.id,
            summary=event["summary"],
            start_time=start_time,
            end_time=end_time,
            attendees=event["attendees"],
            host="human" if self.calendar.get_availability(company.id) else "agent",
            location=event["location"],
            conferencing_link=event["join_link"],
        )

        self.repository.add_meeting(meeting)
        return meeting

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_text_from_file(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from PyPDF2 import PdfReader  # type: ignore
            except ImportError:
                return ""
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix in {".docx", ".doc"}:
            try:
                import docx  # type: ignore
            except ImportError:
                return ""
            doc = docx.Document(str(path))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8")

        mime, _ = mimetypes.guess_type(str(path))
        if mime and mime.startswith("text/"):
            return path.read_text(encoding="utf-8")
        return ""

    def _persist_quote(self, company_id: str, lead: LeadProfile, data: Dict[str, Any]) -> Quote:
        quote = Quote(
            id=uuid.uuid4().hex,
            lead_id=lead.id,
            company_id=company_id,
            price=float(data.get("price", 0.0)),
            currency=data.get("currency", "USD"),
            scope_summary=data.get("scope_summary", ""),
            delivery_timeline=data.get("delivery_timeline", ""),
            assumptions=data.get("assumptions", []),
        )
        self.repository.add_quote(quote)
        lead.quoted_price = quote.price
        lead.proposed_delivery_date = quote.delivery_timeline
        return quote

