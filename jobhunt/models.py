from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Job:
    source: str
    company: str
    title: str
    location: str
    url: str
    posted_at: Optional[datetime]
    description: str = ""
    id: str = ""

    def age_hours(self, now: Optional[datetime] = None) -> Optional[float]:
        if self.posted_at is None:
            return None
        now = now or datetime.now(timezone.utc)
        delta = now - self.posted_at
        return delta.total_seconds() / 3600.0

    def dedup_key(self) -> str:
        return f"{self.company.lower().strip()}::{self.title.lower().strip()}"
