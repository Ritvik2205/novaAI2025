"""
Thread-safe in-memory repository with JSON persistence.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from datetime import datetime

from backend.models.domain import (
    CompanyProfile,
    LeadMessage,
    LeadProfile,
    Meeting,
    OnboardingSession,
    Quote,
    StudentGroup,
)


class CRMRepository:
    """Simple repository layer backed by a JSON document on disk."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self._lock = threading.Lock()
        self._state = {
            "companies": {},
            "onboarding_sessions": {},
            "leads": {},
            "messages": {},
            "meetings": {},
            "quotes": {},
            "student_groups": {},
        }
        self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.storage_path.exists():
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            return
        with self.storage_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        with self._lock:
            for company_id, payload in raw.get("companies", {}).items():
                self._state["companies"][company_id] = CompanyProfile.model_validate(payload)
            for session_id, payload in raw.get("onboarding_sessions", {}).items():
                self._state["onboarding_sessions"][session_id] = OnboardingSession.model_validate(payload)
            for lead_id, payload in raw.get("leads", {}).items():
                self._state["leads"][lead_id] = LeadProfile.model_validate(payload)
            for message_id, payload in raw.get("messages", {}).items():
                self._state["messages"][message_id] = LeadMessage.model_validate(payload)
            for meeting_id, payload in raw.get("meetings", {}).items():
                self._state["meetings"][meeting_id] = Meeting.model_validate(payload)
            for quote_id, payload in raw.get("quotes", {}).items():
                self._state["quotes"][quote_id] = Quote.model_validate(payload)
            for group_id, payload in raw.get("student_groups", {}).items():
                self._state["student_groups"][group_id] = StudentGroup.model_validate(payload)

    def _persist(self) -> None:
        snapshot = {
            "companies": {k: v.model_dump(mode="json") for k, v in self._state["companies"].items()},
            "onboarding_sessions": {
                k: v.model_dump(mode="json") for k, v in self._state["onboarding_sessions"].items()
            },
            "leads": {k: v.model_dump(mode="json") for k, v in self._state["leads"].items()},
            "messages": {k: v.model_dump(mode="json") for k, v in self._state["messages"].items()},
            "meetings": {k: v.model_dump(mode="json") for k, v in self._state["meetings"].items()},
            "quotes": {k: v.model_dump(mode="json") for k, v in self._state["quotes"].items()},
            "student_groups": {k: v.model_dump(mode="json") for k, v in self._state["student_groups"].items()},
        }
        with self.storage_path.open("w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, sort_keys=True, default=str)

    # ------------------------------------------------------------------
    # Company management
    # ------------------------------------------------------------------
    def create_company(self, name: str, website: Optional[str], description: Optional[str]) -> CompanyProfile:
        company_id = uuid.uuid4().hex
        profile = CompanyProfile(id=company_id, name=name, website=website, description=description)
        with self._lock:
            self._state["companies"][company_id] = profile
            self._persist()
        return profile

    def get_company(self, company_id: str) -> Optional[CompanyProfile]:
        with self._lock:
            return self._state["companies"].get(company_id)

    def update_company(self, profile: CompanyProfile) -> CompanyProfile:
        profile.updated_at = datetime.utcnow()
        with self._lock:
            self._state["companies"][profile.id] = profile
            self._persist()
        return profile

    def list_companies(self) -> List[CompanyProfile]:
        with self._lock:
            return list(self._state["companies"].values())

    def attach_document(self, company_id: str, file_path: str) -> None:
        with self._lock:
            profile = self._state["companies"].get(company_id)
            if not profile:
                raise KeyError(f"Company {company_id} not found")
            if file_path not in profile.documents:
                profile.documents.append(file_path)
                profile.updated_at = datetime.utcnow()
            self._persist()

    def add_company_metadata(self, company_id: str, metadata: Dict[str, str]) -> CompanyProfile:
        with self._lock:
            profile = self._state["companies"].get(company_id)
            if not profile:
                raise KeyError(f"Company {company_id} not found")
            profile.metadata.update(metadata)
            profile.updated_at = datetime.utcnow()
            self._persist()
            return profile

    def list_company_documents(self, company_id: str) -> List[str]:
        with self._lock:
            profile = self._state["companies"].get(company_id)
            if not profile:
                raise KeyError(f"Company {company_id} not found")
            return list(profile.documents)

    # ------------------------------------------------------------------
    # Onboarding sessions
    # ------------------------------------------------------------------
    def create_onboarding_session(self, company_id: str, questions: List[str]) -> OnboardingSession:
        session_id = uuid.uuid4().hex
        session = OnboardingSession(session_id=session_id, company_id=company_id, questions=questions)
        with self._lock:
            self._state["onboarding_sessions"][session_id] = session
            self._persist()
        return session

    def get_onboarding_session(self, session_id: str) -> Optional[OnboardingSession]:
        with self._lock:
            return self._state["onboarding_sessions"].get(session_id)

    def save_onboarding_session(self, session: OnboardingSession) -> OnboardingSession:
        session.updated_at = datetime.utcnow()
        with self._lock:
            self._state["onboarding_sessions"][session.session_id] = session
            self._persist()
        return session

    # ------------------------------------------------------------------
    # Lead lifecycle
    # ------------------------------------------------------------------
    def create_lead(
        self,
        company_id: str,
        name: Optional[str],
        email: Optional[str],
        phone: Optional[str],
        initial_notes: Optional[str] = None,
    ) -> LeadProfile:
        lead_id = uuid.uuid4().hex
        lead = LeadProfile(id=lead_id, company_id=company_id, name=name, email=email, phone=phone)
        if initial_notes:
            lead.notes.append(initial_notes)
        with self._lock:
            self._state["leads"][lead_id] = lead
            self._persist()
        return lead

    def get_lead(self, lead_id: str) -> Optional[LeadProfile]:
        with self._lock:
            return self._state["leads"].get(lead_id)

    def list_leads(self, company_id: Optional[str] = None) -> List[LeadProfile]:
        with self._lock:
            leads = list(self._state["leads"].values())
        if company_id:
            return [lead for lead in leads if lead.company_id == company_id]
        return leads

    def update_lead(self, lead: LeadProfile) -> LeadProfile:
        lead.updated_at = datetime.utcnow()
        with self._lock:
            self._state["leads"][lead.id] = lead
            self._persist()
        return lead

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def add_message(
        self,
        lead_id: str,
        sender: str,
        content: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> LeadMessage:
        if metadata is None:
            metadata = {}
        message_id = uuid.uuid4().hex
        message = LeadMessage(message_id=message_id, lead_id=lead_id, sender=sender, content=content, metadata=metadata)
        with self._lock:
            self._state["messages"][message_id] = message
            if lead_id in self._state["leads"]:
                lead = self._state["leads"][lead_id]
                lead.updated_at = datetime.utcnow()
            self._persist()
        return message

    def get_messages(self, lead_id: str) -> List[LeadMessage]:
        with self._lock:
            messages = [
                message
                for message in self._state["messages"].values()
                if message.lead_id == lead_id
            ]
        return sorted(messages, key=lambda msg: msg.created_at)

    # ------------------------------------------------------------------
    # Meetings and quotes
    # ------------------------------------------------------------------
    def add_meeting(self, meeting: Meeting) -> Meeting:
        with self._lock:
            self._state["meetings"][meeting.id] = meeting
            if meeting.lead_id in self._state["leads"]:
                lead = self._state["leads"][meeting.lead_id]
                if meeting.id not in lead.meetings:
                    lead.meetings.append(meeting.id)
                    lead.updated_at = datetime.utcnow()
            self._persist()
        return meeting

    def list_meetings(self, lead_id: Optional[str] = None) -> List[Meeting]:
        with self._lock:
            meetings = list(self._state["meetings"].values())
        if lead_id:
            return [meeting for meeting in meetings if meeting.lead_id == lead_id]
        return meetings

    def add_quote(self, quote: Quote) -> Quote:
        with self._lock:
            self._state["quotes"][quote.id] = quote
            self._persist()
        return quote

    def list_quotes(self, lead_id: str) -> List[Quote]:
        with self._lock:
            return [
                quote
                for quote in self._state["quotes"].values()
                if quote.lead_id == lead_id
            ]

    # ------------------------------------------------------------------
    # Student groups
    # ------------------------------------------------------------------
    def create_student_group(
        self,
        company_id: str,
        *,
        name: str,
        summary: Optional[str],
        focus_areas: List[str],
        past_projects: List[str],
        preferred_tools: List[str],
        contact_email: Optional[str],
        availability: Optional[str],
        profile_image_url: Optional[str],
        metadata: Dict[str, str],
    ) -> StudentGroup:
        group_id = uuid.uuid4().hex
        group = StudentGroup(
            id=group_id,
            company_id=company_id,
            name=name,
            summary=summary,
            focus_areas=focus_areas,
            past_projects=past_projects,
            preferred_tools=preferred_tools,
            contact_email=contact_email,
            availability=availability,
            profile_image_url=profile_image_url,
            metadata=metadata,
        )
        with self._lock:
            self._state["student_groups"][group_id] = group
            self._persist()
        return group

    def upsert_student_group(self, company_id: str, *, name: str, data: Dict[str, str]) -> StudentGroup:
        group_id = data.get("id") or uuid.uuid4().hex
        with self._lock:
            existing = self._state["student_groups"].get(group_id)
            payload = existing.model_dump(mode="python") if existing else {}
            metadata_raw = data.get("metadata", payload.get("metadata", {}))
            if isinstance(metadata_raw, dict):
                metadata = {k: str(v) for k, v in metadata_raw.items()}
            else:
                metadata = {"notes": str(metadata_raw)}
            payload.update(
                {
                    "id": group_id,
                    "company_id": company_id,
                    "name": name,
                    "summary": data.get("summary"),
                    "focus_areas": data.get("focus_areas", payload.get("focus_areas")),
                    "past_projects": data.get("past_projects", payload.get("past_projects")),
                    "preferred_tools": data.get("preferred_tools", payload.get("preferred_tools")),
                    "contact_email": data.get("contact_email", payload.get("contact_email")),
                    "availability": data.get("availability", payload.get("availability")),
                    "profile_image_url": data.get("profile_image_url", payload.get("profile_image_url")),
                    "metadata": metadata,
                    "created_at": payload.get("created_at"),
                    "updated_at": datetime.utcnow(),
                }
            )
            group = StudentGroup.model_validate(payload)
            self._state["student_groups"][group_id] = group
            self._persist()
            return group

    def list_student_groups(self, company_id: Optional[str] = None) -> List[StudentGroup]:
        with self._lock:
            groups = list(self._state["student_groups"].values())
        if company_id:
            return [group for group in groups if group.company_id == company_id]
        return groups

    def remove_student_groups(self, company_id: str) -> None:
        with self._lock:
            to_remove = [
                group_id
                for group_id, group in self._state["student_groups"].items()
                if group.company_id == company_id
            ]
            for group_id in to_remove:
                self._state["student_groups"].pop(group_id, None)
            self._persist()

    def record_lead_handoff(self, lead_id: str, group_id: Optional[str], decision: str) -> LeadProfile:
        with self._lock:
            lead = self._state["leads"].get(lead_id)
            if not lead:
                raise KeyError(f"Lead {lead_id} not found.")
            if group_id:
                lead.metadata["handoff_group_id"] = group_id
            else:
                lead.metadata.pop("handoff_group_id", None)
            lead.metadata["handoff_decision"] = decision
            lead.updated_at = datetime.utcnow()
            self._persist()
            return lead

