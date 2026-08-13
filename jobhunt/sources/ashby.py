"""Ashby public job board API. No auth needed."""
from __future__ import annotations
from datetime import timezone
from html import unescape
import re

import httpx
from dateutil import parser as dtparse

from ..models import Job

API = "https://api.ashbyhq.com/posting-api/job-board/{handle}?includeCompensation=false"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    return unescape(_TAG_RE.sub(" ", html or "")).strip()


async def fetch(client: httpx.AsyncClient, handle: str, keywords: list[str]) -> list[Job]:
    r = await client.get(API.format(handle=handle))
    r.raise_for_status()
    data = r.json()
    kws = [k.lower() for k in keywords]
    out: list[Job] = []
    for j in data.get("jobs", []):
        title = j.get("title") or ""
        desc = _clean(j.get("descriptionHtml") or j.get("descriptionPlain") or "")
        haystack = f"{title}\n{desc}".lower()
        if not any(kw in haystack for kw in kws):
            continue

        published = j.get("publishedDate") or j.get("updatedAt")
        posted = None
        if published:
            try:
                posted = dtparse.parse(published)
                if posted.tzinfo is None:
                    posted = posted.replace(tzinfo=timezone.utc)
            except Exception:
                posted = None

        loc = j.get("location") or ""

        out.append(Job(
            source="ashby",
            company=handle,
            title=title,
            location=loc,
            url=j.get("jobUrl") or j.get("applyUrl") or "",
            posted_at=posted,
            description=desc[:4000],
            id=j.get("id", ""),
        ))
    return out
