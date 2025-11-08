"""
Domain models for the agentic CRM backend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CompanyProfile(BaseModel):
    """High level representation of a contractor-company client."""

    id: str
    name: str
    website: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    knowledge_base_ids: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OnboardingSession(BaseModel):
    """State machine for the onboarding discovery questions."""

    session_id: str
    company_id: str
    questions: List[str]
    answers: List[str] = Field(default_factory=list)
    status: Literal["active", "completed"] = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def next_question(self) -> Optional[str]:
        if self.status == "completed":
            return None
        index = len(self.answers)
        if index >= len(self.questions):
            return None
        return self.questions[index]


class LeadMessage(BaseModel):
    """Single message exchanged with a prospective client."""

    message_id: str
    lead_id: str
    sender: Literal["lead", "agent", "human"] = "lead"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = Field(default_factory=dict)


class LeadProfile(BaseModel):
    """Aggregated view of a lead with preferences and agent notes."""

    id: str
    company_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Literal["new", "engaged", "qualified", "quoted", "won", "lost"] = "new"
    preferences: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    action_items: List[str] = Field(default_factory=list)
    quoted_price: Optional[float] = None
    proposed_delivery_date: Optional[str] = None
    meetings: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            allowed = {"new", "engaged", "qualified", "quoted", "won", "lost"}
            synonyms = {
                "new inquiry": "new",
                "initial": "new",
                "prospect": "engaged",
                "in-progress": "engaged",
                "closed won": "won",
                "closed lost": "lost",
            }
            mapped = synonyms.get(normalized, normalized)
            if mapped in allowed:
                return mapped
        return "new"


class Meeting(BaseModel):
    """Calendar event scheduled by the agent or a human."""

    id: str
    lead_id: str
    company_id: str
    summary: str
    start_time: datetime
    end_time: datetime
    attendees: List[str] = Field(default_factory=list)
    host: Literal["human", "agent"] = "human"
    location: Optional[str] = None
    conferencing_link: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Quote(BaseModel):
    """Quote details emitted by the quoting agent."""

    id: str
    lead_id: str
    company_id: str
    price: float
    currency: str = "USD"
    scope_summary: str
    delivery_timeline: str
    assumptions: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StudentGroup(BaseModel):
    """Profile for a student team available for client projects."""

    id: str
    company_id: str
    name: str
    summary: Optional[str] = None
    focus_areas: List[str] = Field(default_factory=list)
    past_projects: List[str] = Field(default_factory=list)
    preferred_tools: List[str] = Field(default_factory=list)
    contact_email: Optional[str] = None
    availability: Optional[str] = None
    profile_image_url: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("focus_areas", "past_projects", "preferred_tools", mode="before")
    @classmethod
    def normalise_list(cls, value):
        if isinstance(value, str):
            return [segment.strip() for segment in value.split(",") if segment.strip()]
        if value is None:
            return []
        return value

