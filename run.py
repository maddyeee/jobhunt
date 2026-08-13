#!/usr/bin/env python3
"""Entry point: python run.py [--keywords ASIC,FPGA,RTL] [--hours 24]"""
from __future__ import annotations
import argparse
import asyncio
import concurrent.futures
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console

from jobhunt.filters import (
    keyword_filter,
    recency_filter,
    dedupe,
    seniority_filter,
    seniority_filter_offline,
    us_location_filter,
)
from jobhunt.output import print_table, write_markdown_bundle
from jobhunt.sources import fetch_all_sources
from jobhunt.sources.base import LAST_RUN_LOG
from jobhunt.tailor import tailor_projects

DEFAULT_KEYWORDS = [
    "ASIC", "FPGA", "RTL", "UVM", "SystemVerilog",
    "Digital Design", "Verification", "DV",
]
ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily hardware-jobs scanner + resume tailoring")
    p.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated list of role keywords",
    )
    p.add_argument("--hours", type=int, default=24, help="Only include jobs newer than N hours")
    p.add_argument(
        "--out",
        default=None,
        help="Output folder (default: ./jobs_YYYY-MM-DD/)",
    )
    p.add_argument(
        "--no-tailor",
        action="store_true",
        help="Skip Sonnet project-generation (0 LLM cost for the tailoring step). "
             "Haiku seniority classification still runs unless --no-classify is set.",
    )
    p.add_argument(
        "--no-classify",
        action="store_true",
        help="Skip Haiku seniority classification (only hard-exclude regex runs). "
             "Combined with --no-tailor this makes the run essentially free.",
    )
    p.add_argument(
        "--offline-classify",
        action="store_true",
        help="Use offline seniority classifier (regex + YoE extraction from JD text). "
             "No API key needed. Dumber than Haiku but 0 cost.",
    )
    p.add_argument(
        "--all-locations",
        action="store_true",
        help="Disable the US-only location filter (include India/Israel/EU/APAC roles).",
    )
    return p.parse_args()


def _generate_all_bullets(jobs) -> dict[str, str]:
    out: dict[str, str] = {}
    if not jobs:
        return out

    def one(job):
        try:
            return job.dedup_key(), tailor_projects(job)
        except Exception as e:
            return job.dedup_key(), f"*(project generation failed: {e})*"

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for key, bullets in pool.map(one, jobs):
            out[key] = bullets
    return out


def main() -> int:
    args = parse_args()
    console = Console()

    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY is not set. Export it and try again.[/red]")
        return 2

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    console.print(f"[bold]Keywords:[/bold] {', '.join(keywords)}")
    console.print(f"[bold]Window:[/bold] last {args.hours} hours\n")

    companies = yaml.safe_load((ROOT / "companies.yaml").read_text(encoding="utf-8"))

    console.print("[bold]Fetching from all sources…[/bold]")
    raw = asyncio.run(fetch_all_sources(keywords, companies))
    console.print(f"[bold green]Total raw jobs fetched:[/bold green] {len(raw)}\n")

    kw_hits = keyword_filter(raw, keywords)
    console.print(f"After keyword filter: {len(kw_hits)}")

    recent = recency_filter(kw_hits, args.hours)
    console.print(f"After {args.hours}h recency filter: {len(recent)}")

    if not args.all_locations:
        recent = us_location_filter(recent)
        console.print(f"After US-only location filter: {len(recent)}")

    unique = dedupe(recent)
    console.print(f"After dedupe: {len(unique)}")

    if args.no_classify:
        from jobhunt.filters import HARD_EXCLUDE_RE
        qualified = [j for j in unique if not HARD_EXCLUDE_RE.search(j.title)]
        console.print(f"[bold green]Qualified (regex-only, no LLM):[/bold green] {len(qualified)}\n")
    elif args.offline_classify:
        console.print("\n[bold]Filtering by seniority (offline: regex + YoE parser)…[/bold]")
        qualified = seniority_filter_offline(unique)
        console.print(f"[bold green]Qualified (offline classifier):[/bold green] {len(qualified)}\n")
    else:
        console.print("\n[bold]Filtering by seniority (regex + Haiku)…[/bold]")
        qualified = seniority_filter(unique)
        console.print(f"[bold green]Qualified jobs:[/bold green] {len(qualified)}\n")

    print_table(qualified)

    bullets: dict[str, str] = {}
    if qualified and not args.no_tailor:
        console.print("\n[bold]Generating tailored resume projects (Sonnet 4.6)…[/bold]")
        bullets = _generate_all_bullets(qualified)

    out_dir = Path(args.out) if args.out else ROOT / f"jobs_{datetime.now().strftime('%Y-%m-%d')}"
    write_markdown_bundle(qualified, bullets, out_dir)

    # Persist per-source fetch log for future debugging
    log_lines = [
        f"Run: {datetime.now().isoformat(timespec='seconds')}",
        f"Keywords: {', '.join(keywords)}",
        f"Window: last {args.hours}h",
        f"US-only: {not args.all_locations}",
        "",
        "Per-source results:",
        *LAST_RUN_LOG,
        "",
        f"After keyword filter: {len(kw_hits)}",
        f"After recency+location+dedupe: {len(unique)}",
        f"Qualified: {len(qualified)}",
    ]
    (out_dir / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    console.print(f"\n[bold]Written to:[/bold] {out_dir}")
    console.print("Open INDEX.md for the full list, or run.log for per-source status.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
