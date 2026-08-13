"""AMD careers API (iCIMS-backed, public JSON — no auth needed).
Endpoint: https://careers.amd.com/api/jobs
"""
from __future__ import annotations
from datetime import timezone

import httpx
from dateutil import parser as dtparse

from ..models import Job

API = "https://careers.amd.com/api/jobs"
PAGE_SIZE = 20


async def fetch(client: httpx.AsyncClient, keywords: list[str]) -> list[Job]:
    kws = [k.lower() for k in keywords]
    out: list[Job] = []
    seen: set[str] = set()
    headers = {"Accept": "application/json"}

    for kw in keywords:
        for page in range(1, 8):  # up to 7 pages × 20 = 140 per keyword
            params = {
                "query": kw,
                "location": "United States",
                "pagesize": PAGE_SIZE,
                "page": page,
            }
            r = await client.get(API, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            jobs = data.get("jobs") or []
            if not jobs:
                break

            for item in jobs:
                j = item.get("data") or {}
                slug = j.get("slug") or j.get("req_id") or ""
                if not slug or slug in seen:
                    continue
                seen.add(slug)

                title = j.get("title") or ""
                desc = (j.get("description") or "") + " " + (j.get("qualifications") or "")
                haystack = f"{title} {desc}".lower()
                if not any(k in haystack for k in kws):
                    continue

                posted = None
                pd = j.get("posted_date")
                if pd:
                    try:
                        posted = dtparse.parse(pd)
                        if posted.tzinfo is None:
                            posted = posted.replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

                loc = j.get("full_location") or j.get("short_location") or j.get("city") or ""
                url = f"https://careers.amd.com/careers-home/jobs/{slug}/job"

                out.append(Job(
                    source="amd_icims",
                    company="AMD",
                    title=title,
                    location=loc,
                    url=url,
                    posted_at=posted,
                    description=desc[:4000],
                    id=slug,
                ))

            if len(jobs) < PAGE_SIZE:
                break

    return out
