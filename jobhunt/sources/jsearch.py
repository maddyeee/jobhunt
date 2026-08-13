"""JSearch on RapidAPI — aggregates LinkedIn/Indeed/ZipRecruiter etc.
Free tier: 200 requests/month. Set RAPIDAPI_KEY in env.

Accepts a full pre-built query string so callers can pass either generic
keyword combos ("ASIC RTL verification engineer") or company-targeted ones
("Apple ASIC RTL verification engineer").
"""
from __future__ import annotations
from datetime import datetime, timezone
import os

import httpx

from ..models import Job

URL = "https://jsearch.p.rapidapi.com/search"


async def fetch(client: httpx.AsyncClient, query: str) -> list[Job]:
    key = os.getenv("RAPIDAPI_KEY")
    if not key:
        return []
    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": query,
        "page": "1",
        "num_pages": "1",
        "date_posted": "today",
        "country": "us",
    }
    r = await client.get(URL, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    out: list[Job] = []
    for j in data.get("data", []) or []:
        ts = j.get("job_posted_at_timestamp")
        posted = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        loc = ", ".join(
            filter(None, [j.get("job_city"), j.get("job_state"), j.get("job_country")])
        )
        out.append(Job(
            source="jsearch",
            company=j.get("employer_name") or "",
            title=j.get("job_title") or "",
            location=loc,
            url=j.get("job_apply_link") or j.get("job_google_link") or "",
            posted_at=posted,
            description=(j.get("job_description") or "")[:4000],
            id=j.get("job_id", ""),
        ))
    return out
