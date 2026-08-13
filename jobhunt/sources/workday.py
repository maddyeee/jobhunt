"""Workday CxS API scraping. Public unauthenticated endpoint used by the
JS SPA to load jobs. Format:
  POST https://<sub>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs
Body:
  {"appliedFacets":{}, "limit": 20, "offset": 0, "searchText": "<keyword>"}
Response fields per job: title, externalPath, locationsText, postedOn ("Posted Yesterday" / "Posted 3 Days Ago").
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import re

import httpx

from ..models import Job

_POST_RE = re.compile(
    r"(?:posted\s+)?(?:(\d+)\+?\s+days?\s+ago|(yesterday|today))",
    re.IGNORECASE,
)


def _parse_posted(txt: str, now: datetime) -> datetime | None:
    if not txt:
        return None
    m = _POST_RE.search(txt)
    if not m:
        return None
    if m.group(1):
        return now - timedelta(days=int(m.group(1)))
    word = (m.group(2) or "").lower()
    if word == "today":
        return now
    if word == "yesterday":
        return now - timedelta(days=1)
    return None


def _detail_url(base_api_url: str, external_path: str) -> str:
    # base_api_url is like https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/External/jobs
    # canonical public URL is https://intel.wd1.myworkdayjobs.com/en-US/External<externalPath>
    m = re.match(r"(https://[^/]+)/wday/cxs/[^/]+/([^/]+)/jobs", base_api_url)
    if not m:
        return external_path
    host, site = m.group(1), m.group(2)
    if not external_path.startswith("/"):
        external_path = "/" + external_path
    return f"{host}/en-US/{site}{external_path}"


async def fetch(
    client: httpx.AsyncClient,
    name: str,
    base_url: str,
    keywords: list[str],
) -> list[Job]:
    out: list[Job] = []
    seen_paths: set[str] = set()
    now = datetime.now(timezone.utc)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    for kw in keywords:
        offset = 0
        page = 0
        while page < 5:  # up to 5*20=100 jobs per keyword per company
            body = {
                "appliedFacets": {},
                "limit": 20,
                "offset": offset,
                "searchText": kw,
            }
            r = await client.post(base_url, json=body, headers=headers)
            if r.status_code != 200:
                break
            data = r.json()
            postings = data.get("jobPostings") or []
            if not postings:
                break
            for j in postings:
                path = j.get("externalPath") or ""
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                title = j.get("title") or ""
                posted = _parse_posted(j.get("postedOn") or "", now)
                out.append(Job(
                    source="workday",
                    company=name,
                    title=title,
                    location=j.get("locationsText") or "",
                    url=_detail_url(base_url, path),
                    posted_at=posted,
                    description="",  # workday JD fetch is a separate call; skip for filter speed
                    id=j.get("bulletFields", [""])[0] if j.get("bulletFields") else path,
                ))
            if len(postings) < 20:
                break
            offset += 20
            page += 1
    return out
