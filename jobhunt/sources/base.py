"""Concurrent fan-out across every configured source. Each fetcher returns a
list[Job]; failures are logged but don't kill the run.

Aggregator query strategy
--------------------------
Free-tier limits:
  JSearch  (RapidAPI) : 200 req/month → ~6/day for daily runs
  SerpAPI (Google Jobs): 100 req/month → ~3/day for daily runs

To maximise coverage while staying in free tiers, we split the load:

  JSearch  → 3 combined generic keyword queries  (broad coverage)
  SerpAPI  → company-targeted queries, one per aggregator_target
             (catches Apple, Google, Qualcomm, etc. that can't be scraped)

If the aggregator_targets list is long, SerpAPI calls are batched so we never
exceed 3 per run.  Excess targets fall back to JSearch company-targeted queries
(which has a higher free budget).
"""
from __future__ import annotations
import asyncio
import os
from typing import Any

import httpx

from ..models import Job
from . import greenhouse, lever, ashby, workday, amd_icims, jsearch, adzuna, serpapi_google

LAST_RUN_LOG: list[str] = []

# Max SerpAPI calls per run to stay inside 100/month on daily use.
# Increase this if you're on a paid tier.
SERPAPI_MAX_PER_RUN = 3
JSEARCH_MAX_PER_RUN = 6


async def _safe(name: str, coro):
    try:
        jobs = await coro
        line = f"  [{name}] {len(jobs)} jobs"
        print(line)
        LAST_RUN_LOG.append(line)
        return jobs
    except Exception as e:
        line = f"  [{name}] FAILED: {type(e).__name__}: {e}"
        print(line)
        LAST_RUN_LOG.append(line)
        return []


def _build_generic_queries(keywords: list[str]) -> list[str]:
    """Collapse 8 loose keywords into ≤3 meaningful grouped query strings."""
    kw = [k.strip() for k in keywords if k.strip()]
    if not kw:
        return ["ASIC RTL verification engineer"]
    # Group into at most 3 buckets so we don't burn API credits on near-duplicates.
    buckets: list[list[str]] = [[], [], []]
    for i, k in enumerate(kw):
        buckets[i % 3].append(k)
    return [" ".join(b) + " engineer" for b in buckets if b]


def _build_company_query(company: str, keywords: list[str]) -> str:
    """Build a targeted query: '<company> ASIC RTL verification engineer'."""
    # Use up to 3 of the most domain-specific keywords to keep the query tight.
    domain_kws = [k for k in keywords if k.upper() not in ("DIGITAL DESIGN", "VERIFICATION", "DV")]
    sample = (domain_kws or keywords)[:3]
    return f"{company} {' '.join(sample)} engineer"


async def fetch_all_sources(
    keywords: list[str],
    companies: dict[str, Any],
) -> list[Job]:
    LAST_RUN_LOG.clear()
    timeout = httpx.Timeout(60.0, connect=15.0)
    limits = httpx.Limits(max_connections=30, max_keepalive_connections=10)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
    }

    aggregator_targets: list[str] = companies.get("aggregator_targets") or []
    has_serpapi  = bool(os.getenv("SERPAPI_KEY"))
    has_jsearch  = bool(os.getenv("RAPIDAPI_KEY"))
    has_adzuna   = bool(os.getenv("ADZUNA_APP_ID")) and bool(os.getenv("ADZUNA_APP_KEY"))

    generic_queries = _build_generic_queries(keywords)

    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers) as client:
        tasks: list[asyncio.Task] = []

        # ── Direct ATS sources ────────────────────────────────────────────
        for handle in companies.get("greenhouse") or []:
            tasks.append(asyncio.create_task(
                _safe(f"greenhouse:{handle}", greenhouse.fetch(client, handle, keywords))
            ))
        for handle in companies.get("lever") or []:
            tasks.append(asyncio.create_task(
                _safe(f"lever:{handle}", lever.fetch(client, handle, keywords))
            ))
        for handle in companies.get("ashby") or []:
            tasks.append(asyncio.create_task(
                _safe(f"ashby:{handle}", ashby.fetch(client, handle, keywords))
            ))
        for entry in companies.get("workday") or []:
            if entry.get("kind", "workday") == "workday":
                tasks.append(asyncio.create_task(
                    _safe(f"workday:{entry['name']}", workday.fetch(
                        client, entry["name"], entry["url"], keywords
                    ))
                ))

        # ── Dedicated company API fetchers ────────────────────────────────
        tasks.append(asyncio.create_task(
            _safe("amd", amd_icims.fetch(client, keywords))
        ))

        # ── Aggregators ───────────────────────────────────────────────────
        # JSearch: generic keyword queries + overflow company targets
        if has_jsearch:
            jsearch_calls = 0
            for q in generic_queries:
                if jsearch_calls >= JSEARCH_MAX_PER_RUN:
                    break
                tasks.append(asyncio.create_task(
                    _safe(f"jsearch:{q[:30]}", jsearch.fetch(client, q))
                ))
                jsearch_calls += 1

        # SerpAPI: company-targeted queries (primary) + overflow to JSearch + Adzuna
        targeted_companies: set[str] = set()
        serp_calls = 0
        jsearch_overflow = 0
        for company in aggregator_targets:
            q = _build_company_query(company, keywords)
            if has_serpapi and serp_calls < SERPAPI_MAX_PER_RUN:
                tasks.append(asyncio.create_task(
                    _safe(f"serpapi:{company}", serpapi_google.fetch(client, q))
                ))
                serp_calls += 1
                targeted_companies.add(company)
            elif has_jsearch and (jsearch_calls + jsearch_overflow) < JSEARCH_MAX_PER_RUN:
                tasks.append(asyncio.create_task(
                    _safe(f"jsearch:{company}", jsearch.fetch(client, q))
                ))
                jsearch_overflow += 1
                targeted_companies.add(company)

        # Adzuna: generic keyword queries + overflow for companies with no targeted slot
        if has_adzuna:
            for kw in keywords:
                tasks.append(asyncio.create_task(
                    _safe(f"adzuna:{kw}", adzuna.fetch(client, kw))
                ))
            adzuna_overflow = 0
            for company in aggregator_targets:
                if company not in targeted_companies and adzuna_overflow < 10:
                    q = _build_company_query(company, keywords)
                    tasks.append(asyncio.create_task(
                        _safe(f"adzuna:{company}", adzuna.fetch(client, q))
                    ))
                    adzuna_overflow += 1

        results = await asyncio.gather(*tasks)

    flat: list[Job] = []
    for r in results:
        flat.extend(r)
    return flat
