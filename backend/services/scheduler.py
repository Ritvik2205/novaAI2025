"""
Calendar orchestration helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CalendarService:
    """Minimal calendar integration with pluggable providers."""

    def __init__(self, provider: str, credentials_path: Optional[str]):
        self.provider = provider
        self.credentials_path = credentials_path
        self._availability: Dict[str, List[Dict[str, str]]] = {}

    # ------------------------------------------------------------------
    # Availability management
    # ------------------------------------------------------------------
    def set_availability(self, company_id: str, windows: List[Dict[str, str]]) -> None:
        """Store availability windows for a company."""

        logger.info("Updating availability for company %s (%s slots)", company_id, len(windows))
        self._availability[company_id] = windows

    def get_availability(self, company_id: str) -> List[Dict[str, str]]:
        """Return cached availability windows."""

        return self._availability.get(company_id, [])

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def find_slot(
        self,
        company_id: str,
        preferred_start: datetime,
        meeting_duration: timedelta,
    ) -> Optional[Dict[str, datetime]]:
        """Find the next available slot; crude fallback until provider integration is added."""

        windows = self.get_availability(company_id)
        for window in windows:
            start = datetime.fromisoformat(window["start"])
            end = datetime.fromisoformat(window["end"])
            slot_end = preferred_start + meeting_duration
            if start <= preferred_start and slot_end <= end:
                return {"start": preferred_start, "end": slot_end}
        return None

    def schedule_event(
        self,
        company_id: str,
        lead_name: str,
        attendees: List[str],
        start_time: datetime,
        end_time: datetime,
        title: str,
        location: Optional[str] = None,
    ) -> Dict[str, str]:
        """Return event payload instead of calling real API for now."""

        logger.info(
            "Scheduling placeholder event for company %s with attendees=%s",
            company_id,
            attendees,
        )
        return {
            "summary": title,
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "attendees": attendees,
            "location": location or "TBD",
            "join_link": f"https://meet.agentic.crm/{company_id}-{lead_name.replace(' ', '').lower()}",
        }

