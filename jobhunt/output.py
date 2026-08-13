"""Terminal table + per-job markdown file writing."""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .filters import bay_area_city, location_priority
from .models import Job


def _region_label(loc: str) -> str:
    prio = location_priority(loc)
    if prio == 0:
        return bay_area_city(loc) or "Bay Area"
    if prio == 1:
        return "CA"
    if prio == 2:
        return "US"
    return "?"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(s: str) -> str:
    return _SLUG_RE.sub("-", s.lower()).strip("-")[:50]


def _sort_key(j: Job):
    return (location_priority(j.location), j.age_hours() if j.age_hours() is not None else 9999)


def print_table(jobs: list[Job]) -> None:
    console = Console()
    if not jobs:
        console.print("[yellow]No matching jobs found in the last window.[/yellow]")
        return
    table = Table(title=f"{len(jobs)} matching jobs (Bay Area first)", show_lines=False, expand=True)
    table.add_column("Region", style="yellow", no_wrap=True)
    table.add_column("Company", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Location", style="dim")
    table.add_column("Age", justify="right", style="green")
    table.add_column("Source", style="magenta")
    table.add_column("Link", overflow="fold", style="blue")
    for j in sorted(jobs, key=_sort_key):
        age = j.age_hours()
        age_str = f"{age:.1f}h" if age is not None else "?"
        region = _region_label(j.location)
        table.add_row(region, j.company, j.title[:60], j.location[:30], age_str, j.source, j.url)
    console.print(table)


def write_markdown_bundle(
    jobs: list[Job],
    bullets: dict[str, str],
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Per-job files
    for j in jobs:
        fname = f"{_slug(j.company)}__{_slug(j.title)}.md"
        content = _job_markdown(j, bullets.get(j.dedup_key(), "*(bullet generation failed)*"))
        (out_dir / fname).write_text(content, encoding="utf-8")

    # Index file — grouped by region (Bay Area first)
    groups: dict[int, list[Job]] = {0: [], 1: [], 2: [], 3: []}
    for j in jobs:
        groups[location_priority(j.location)].append(j)

    idx = ["# Jobs found — " + datetime.now().strftime("%Y-%m-%d %H:%M"),
           "", f"{len(jobs)} matching roles.", ""]
    region_titles = {
        0: "## Bay Area",
        1: "## California (other)",
        2: "## United States (other)",
        3: "## Unknown / Remote",
    }
    for prio in (0, 1, 2, 3):
        bucket = groups[prio]
        if not bucket:
            continue
        idx.append(region_titles[prio])
        idx.append("")
        for j in sorted(bucket, key=lambda x: (x.age_hours() or 999)):
            age = j.age_hours()
            age_str = f"{age:.1f}h" if age is not None else "?"
            fname = f"{_slug(j.company)}__{_slug(j.title)}.md"
            idx.append(
                f"- **{j.company}** — [{j.title}]({fname}) · {j.location or '—'} · {age_str} · [apply]({j.url})"
            )
        idx.append("")
    (out_dir / "INDEX.md").write_text("\n".join(idx) + "\n", encoding="utf-8")


def _job_markdown(j: Job, bullets: str) -> str:
    age = j.age_hours()
    age_str = f"{age:.1f} hours ago" if age is not None else "unknown"
    return f"""# {j.title}
**Company:** {j.company}
**Location:** {j.location or '—'}
**Posted:** {age_str}
**Source:** {j.source}
**Apply:** {j.url}

---

## Tailored resume projects (copy-paste into your resume)

{bullets}

---

## Job description snippet

{j.description[:2000] if j.description else '*(description not fetched for this source — click Apply to view)*'}
"""
