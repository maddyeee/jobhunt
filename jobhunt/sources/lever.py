"""Lever public postings API. No auth needed."""
from __future__ import annotations
from datetime import datetime, timezone
from html import unescape
import re

import httpx

from ..models import Job

API = "https://api.lever.co/v0/postings/{handle}?mode=json"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    return unescape(_TAG_RE.sub(" ", html or "")).strip()


async def fetch(client: httpx.AsyncClient, handle: str, keywords: list[str]) -> list[Job]:
    r = await client.get(API.format(handle=handle))
    r.raise_for_status()
    data = r.json()
    kws = [k.lower() for k in keywords]
    out: list[Job] = []
    for j in data:
        title = j.get("text") or ""
        desc = _clean(j.get("descriptionPlain") or j.get("description") or "")
        lists = j.get("lists") or []
        extra = " ".join(_clean(item.get("content", "")) for item in lists)
        haystack = f"{title}\n{desc}\n{extra}".lower()
        if not any(kw in haystack for kw in kws):
            continue

        created_ms = j.get("createdAt")
        posted = None
        if created_ms:
            try:
                posted = datetime.fromtimestamp(int(created_ms) / 1000.0, tz=timezone.utc)
            except Exception:
                posted = None

        cats = j.get("categories") or {}
        loc = cats.get("location", "") or ""

        out.append(Job(
            source="lever",
            company=handle,
            title=title,
            location=loc,
            url=j.get("hostedUrl") or j.get("applyUrl") or "",
            posted_at=posted,
            description=(desc + "\n" + extra)[:4000],
            id=j.get("id", ""),
        ))
    return out
