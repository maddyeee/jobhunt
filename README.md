# jobhunt

Daily terminal tool that scours ~50+ semiconductor company career portals for **digital hardware design & verification** roles posted in the last 24 hours, filters to what a 2–3 YoE candidate can realistically apply to, and generates 2–3 tailored resume projects per role using Claude.

Built for: MS EE student with 2+ yrs SoC RTL verification at ARM. All resume context lives in `resume_context.txt` — edit that file if your background changes.

## What it does, in one run

1. Fetches jobs in parallel from:
   - **Greenhouse** public JSON (Tenstorrent, Rivos, Groq, Cerebras, SambaNova, Astera Labs, Lightmatter, d-Matrix, Positron, Etched, Rain, and ~20 more)
   - **Lever** public JSON (Ampere, Marvell/Nuvia, and others)
   - **Ashby** public JSON (newer AI-hardware startups)
   - **Workday** CxS API (Intel, Apple, Qualcomm, Broadcom, NVIDIA, AMD, Micron, TI, Marvell, Analog Devices, NXP, Microchip, Renesas, Infineon)
   - **JSearch (RapidAPI)**, **Adzuna**, **SerpAPI Google Jobs** — only if the corresponding env var is set
2. Keyword-filters (ASIC, FPGA, RTL, UVM, SystemVerilog, Digital Design, Verification, DV — configurable via `--keywords`).
3. 24-hour recency filter (configurable via `--hours`).
4. Deduplicates across sources.
5. Seniority filter, two-stage:
   - Regex drops the obvious: Director / Manager / VP / Head of / Chief / Fellow / Distinguished.
   - **Claude Haiku 4.5** classifies borderline titles (Senior, Staff, Principal, Architect) against your profile so "ASIC Architect Engineer" gets kept if the JD says <=5 YoE, and "Principal Design Engineer, 10+ YoE required" gets dropped.
6. For each surviving job, **Claude Sonnet 4.6** writes 2–3 project entries tailored to that JD, ready to paste into your resume.
7. Prints a terminal table + writes `jobs_YYYY-MM-DD/` folder with one markdown file per job and an `INDEX.md`.

## Setup (one-time)

```bash
cd ~/Desktop/jobhunt
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at minimum:

```
ANTHROPIC_API_KEY=sk-ant-...
```

The optional keys (`RAPIDAPI_KEY`, `ADZUNA_APP_ID`/`_KEY`, `SERPAPI_KEY`) add extra coverage from aggregators (LinkedIn/Indeed/Google Jobs). The tool skips those sources cleanly if a key is missing.

Then load the env vars into your shell each session:

```bash
set -a; source .env; set +a
```

Or add this line to `~/.zshrc` so it's automatic:

```bash
[ -f ~/Desktop/jobhunt/.env ] && set -a && source ~/Desktop/jobhunt/.env && set +a
```

## Daily usage

```bash
cd ~/Desktop/jobhunt
source .venv/bin/activate
python run.py
```

Output ends up in `~/Desktop/jobhunt/jobs_2026-08-13/` (folder name = today's date). Open `INDEX.md` in that folder for the full list; open any per-job `.md` for the tailored project bullets.

### Flags

```
--keywords "ASIC,FPGA,RTL,UVM"    # comma-separated keyword list
--hours 24                        # recency window; try 48 or 72 on Mondays
--no-tailor                       # skip Sonnet project generation (job links only, no bullets)
--no-classify                     # skip Haiku seniority classification too — 0 LLM cost
--offline-classify                # smart seniority via regex + YoE parser (0 cost, no API)
--all-locations                   # disable US-only filter (include India/EU/APAC roles)
--out ./somewhere/                # custom output folder
```

### Free / cheap modes

- **Free + basic filter:** `python run.py --no-tailor --no-classify` — pure fetch + hard-exclude regex. Zero LLM cost. Dumbest filter (won't drop "Principal 10+ YoE" titles).
- **Free + smart filter:** `python run.py --no-tailor --offline-classify` — regex plus a YoE parser that reads the JD and drops roles requiring 6+ years. **This is the recommended free mode.**
- **Cheap + smartest filter, no bullets:** `python run.py --no-tailor` — Haiku classifier (~$0.01–0.05 per run) but no Sonnet bullets. Best when you just want today's job list.
- **Full pipeline:** `python run.py` — Haiku filter + Sonnet-tailored resume bullets per job (~$0.20–0.50 per run).

### Location behavior (default)

The tool defaults to **US-only** and sorts results by region so Bay Area jobs come first:

1. **Bay Area** — San Jose, San Francisco, Santa Clara, Sunnyvale, Palo Alto, Cupertino, Fremont, etc.
2. **California** (other, e.g. San Diego, Irvine, LA)
3. **United States** (other)
4. **Unknown / Remote**

Pass `--all-locations` to include roles outside the US.

## Editing the company list

Open `companies.yaml` and add/remove company handles under `greenhouse:`, `lever:`, `ashby:`, or `workday:`.

- Greenhouse handle = the slug from `boards.greenhouse.io/<handle>`.
- Lever handle = the slug from `jobs.lever.co/<handle>`.
- Ashby handle = the slug from `jobs.ashbyhq.com/<handle>`.
- Workday: paste the CxS API URL (find one job on that career site, open DevTools → Network, look for a POST to `.../wday/cxs/.../jobs`).

## Editing your resume context

`resume_context.txt` holds your experience + education verbatim. The LLM sees this so the projects it suggests don't duplicate what you've already done. Edit this file directly when your resume changes.

## Cost

Approximately **$0.20–0.50 per daily run**, dominated by Sonnet 4.6 project generation. Haiku classification is ~$0.001 per borderline title. You can drop the cost to ~$0 by running with `--no-tailor` when you just want to see today's postings.

## Troubleshooting

- **`ANTHROPIC_API_KEY not set`** — you forgot to `source .env`.
- **Which sources ran and how many jobs each returned** — open `jobs_YYYY-MM-DD/run.log`. Every source is logged with its job count or the error it hit.
- **A specific company returns 0 jobs** — its handle may be wrong or that day may genuinely have zero postings. Try `curl` on the API URL directly to verify.
- **Workday returns 404 or 422** — the tenant/site slug in the URL is wrong. Fix: open the company's careers page in Chrome → DevTools → Network → filter "jobs" → click Search → copy the POST URL (looks like `.../wday/cxs/<tenant>/<site>/jobs`) and paste it into `companies.yaml`.
- **Broken Workday tenants as of 2026-08-13:** Qualcomm, AMD, Broadcom, TI, Microchip, Renesas, Infineon — all commented out in `companies.yaml` with a note. Uncomment and fix the URLs to re-enable.
- **Too many/too few borderline titles being kept** — edit the system prompt in `jobhunt/filters.py` (`_llm_classify` function), or bump the YoE cutoff in `_offline_qualifies` for the offline mode.
