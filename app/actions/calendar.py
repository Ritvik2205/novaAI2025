from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from app.config import get_settings


def suggest_slots(count: int = 2) -> List[str]:
    tz = get_settings().default_timezone
    base = datetime.utcnow().replace(hour=17, minute=0, second=0, microsecond=0)
    return [(base + timedelta(days=i)).isoformat() + f" ({tz})" for i in range(1, count + 1)]
