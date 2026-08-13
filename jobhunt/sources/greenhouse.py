"""Greenhouse public boards API. No auth needed."""
from __future__ import annotations
from datetime import datetime, timezone
from html import unescape
import re

import httpx
from dateutil import parser as dtparse

from ..models import Job

API = "https://boards-api.greenhouse.io/v1/boards/{handle}/jobs?content=true"
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
        content = _clean(j.get("content") or "")
        haystack = f"{title}\n{content}".lower()
        if not any(kw in haystack for kw in kws):
            continue

        updated = j.get("updated_at") or j.get("first_published")
        posted = None
        if updated:
            try:
                posted = dtparse.parse(updated)
                if posted.tzinfo is None:
                    posted = posted.replace(tzinfo=timezone.utc)
            except Exception:
                posted = None

        loc = ""
        if isinstance(j.get("location"), dict):
            loc = j["location"].get("name", "")

        out.append(Job(
            source="greenhouse",
            company=handle,
            title=title,
            location=loc,
            url=j.get("absolute_url", ""),
            posted_at=posted,
            description=content[:4000],
            id=str(j.get("id", "")),
        ))
    return out
