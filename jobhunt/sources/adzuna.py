"""Adzuna API. Free 1000 req/month. Requires ADZUNA_APP_ID + ADZUNA_APP_KEY."""
from __future__ import annotations
from datetime import timezone
import os

import httpx
from dateutil import parser as dtparse

from ..models import Job

URL = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"


async def fetch(client: httpx.AsyncClient, keyword: str) -> list[Job]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": "50",
        "what": f"{keyword} engineer",
        "max_days_old": "1",
        "content-type": "application/json",
    }
    r = await client.get(URL.format(page=1), params=params)
    r.raise_for_status()
    data = r.json()
    out: list[Job] = []
    for j in data.get("results", []) or []:
        created = j.get("created")
        posted = None
        if created:
            try:
                posted = dtparse.parse(created)
                if posted.tzinfo is None:
                    posted = posted.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        loc_obj = j.get("location") or {}
        loc = loc_obj.get("display_name", "") if isinstance(loc_obj, dict) else ""
        comp_obj = j.get("company") or {}
        comp = comp_obj.get("display_name", "") if isinstance(comp_obj, dict) else ""
        out.append(Job(
            source="adzuna",
            company=comp,
            title=j.get("title") or "",
            location=loc,
            url=j.get("redirect_url") or "",
            posted_at=posted,
            description=(j.get("description") or "")[:4000],
            id=str(j.get("id", "")),
        ))
    return out
