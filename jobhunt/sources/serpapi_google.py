"""SerpAPI Google Jobs. Free 100 searches/month. Set SERPAPI_KEY.

Accepts a full pre-built query string so callers can pass either generic
keyword combos or company-targeted queries like "Apple ASIC RTL engineer".
Uses chips=date_posted:today for recency; for company-targeted queries the
caller should NOT add a chips company_name filter since Google Jobs company
matching on chips is unreliable — the query string company name is enough.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import os
import re

import httpx

from ..models import Job

URL = "https://serpapi.com/search.json"
_AGE_RE = re.compile(r"(\d+)\s*(hour|day|minute)s?\s*ago", re.IGNORECASE)


def _parse_age(txt: str) -> datetime | None:
    if not txt:
        return None
    m = _AGE_RE.search(txt)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    now = datetime.now(timezone.utc)
    if unit == "hour":
        return now - timedelta(hours=n)
    if unit == "day":
        return now - timedelta(days=n)
    return now - timedelta(minutes=n)


async def fetch(client: httpx.AsyncClient, query: str) -> list[Job]:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        return []
    params = {
        "engine": "google_jobs",
        "q": query,
        "hl": "en",
        "chips": "date_posted:today",
        "api_key": key,
    }
    r = await client.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    out: list[Job] = []
    for j in data.get("jobs_results", []) or []:
        extensions = j.get("detected_extensions") or {}
        posted_txt = extensions.get("posted_at") or ""
        posted = _parse_age(posted_txt)
        link = ""
        opts = j.get("apply_options") or []
        if opts:
            link = opts[0].get("link", "")
        out.append(Job(
            source="serpapi_google",
            company=j.get("company_name") or "",
            title=j.get("title") or "",
            location=j.get("location") or "",
            url=link or j.get("share_link", ""),
            posted_at=posted,
            description=(j.get("description") or "")[:4000],
            id=j.get("job_id", ""),
        ))
    return out
