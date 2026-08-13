# Usage Guide

Complete reference for running the job-hunt CLI — all modes, company coverage, and exact API credit costs per run.

---

## Quick reference

| Goal | Command | APIs used | Est. cost |
|---|---|---|---|
| Just job links, totally free | `python run.py --no-tailor --no-classify` | None | $0 |
| Job links + smart seniority, free | `python run.py --no-tailor --offline-classify` | None | $0 |
| Job links + AI seniority, no bullets | `python run.py --no-tailor` | Claude Haiku | ~$0.02–0.05 |
| Full pipeline (links + bullets) | `python run.py` | Claude Haiku + Sonnet | ~$0.15–0.55 |
| Extend window (e.g. after a weekend) | `python run.py --hours 72 --no-tailor` | Claude Haiku | ~$0.02–0.05 |
| Include non-US roles | `python run.py --all-locations --no-tailor` | Claude Haiku | ~$0.02–0.05 |

---

## All flags

```
python run.py [options]

--keywords "ASIC,FPGA,RTL"     Comma-separated role keywords to search.
                                Default: ASIC, FPGA, RTL, UVM, SystemVerilog,
                                         Digital Design, Verification, DV

--hours N                       Only include jobs posted in the last N hours.
                                Default: 24. Use 48 or 72 on Mondays or after
                                holidays to catch jobs posted over the weekend.

--no-tailor                     Skip Claude Sonnet project-bullet generation.
                                Job links and JD summaries are still written to
                                markdown files; the tailored-projects section is
                                omitted. Saves ~$0.10–0.50 per run.

--offline-classify              Use the offline seniority classifier instead of
                                Claude Haiku. Reads YoE requirements from the JD
                                text with regex (e.g. "5+ years"). Keeps roles
                                where min YoE ≤ 5, drops roles requiring a PhD or
                                asking you to manage a team. Free, but less
                                accurate than Haiku on ambiguous titles.

--no-classify                   Skip seniority filtering entirely. Only the hard
                                regex (Manager / Director / VP / Head of / Chief /
                                Fellow / Distinguished) is applied. Cheapest
                                option; over-includes roles you won't qualify for.

--all-locations                 Disable the US-only location filter. Includes
                                roles in India, Israel, EU, APAC, etc.
                                Bay Area → CA → other US sort order is preserved
                                for roles that do have a US location.

--out ./path/to/folder          Custom output folder instead of the default
                                jobs_YYYY-MM-DD/ in the project root.
```

---

## Mode details

### Mode 1 — Totally free (`--no-tailor --no-classify`)

```bash
python run.py --no-tailor --no-classify
```

- Fetches from all sources (Greenhouse, Lever, Ashby, Workday, AMD iCIMS, JSearch, SerpAPI, Adzuna).
- Applies only the hard-exclude regex: drops Director / Manager / VP / Head of / Chief / Fellow / Distinguished.
- **No Anthropic API calls at all.**
- Output: terminal table + `jobs_YYYY-MM-DD/INDEX.md` with links. Per-job markdown files are written but the tailored-projects section says "generation skipped."
- **Best for:** daily triage when you just want to see what's posted and decide manually.

### Mode 2 — Free + smart seniority (`--no-tailor --offline-classify`)

```bash
python run.py --no-tailor --offline-classify
```

- Same as Mode 1 but also runs an offline YoE parser on each job's description.
- Drops roles where the JD explicitly states 6+ years required, "PhD required", or "manage a team."
- Keeps roles where YoE is ≤ 5 or not stated (fails open — better to over-include than miss a role).
- **No Anthropic API calls.**
- **Best for:** daily free use with smarter noise reduction. This is the recommended default if you want $0 cost.

### Mode 3 — AI seniority, no bullets (`--no-tailor`)

```bash
python run.py --no-tailor
```

- Runs Claude Haiku 4.5 to classify every borderline title (Senior, Architect, Staff, Principal, etc.).
- Haiku reads the job title + first 1500 chars of the JD and decides YES/NO based on your profile (2+ yrs SoC RTL verif, MS in progress).
- Correctly keeps "Server SoC System Architect" (IC role, 3+ YoE stated), drops "Principal Design Engineer, 10+ YoE."
- Skips Sonnet project generation.
- **Best for:** daily use when you want the smartest filter but don't need resume bullets right away.

### Mode 4 — Full pipeline (default)

```bash
python run.py
```

- Runs Haiku classification **and** Sonnet 4.6 project generation.
- For every qualifying job, Sonnet writes 2–3 tailored resume projects (title + 3–4 bullets each) that mirror the JD's exact keywords, complement your existing ARM experience, and are realistic for an MS student to build.
- Output per job: JD summary + tailored projects in a single markdown file ready to copy-paste.
- **Best for:** jobs you're actively applying to. Run Mode 2 or 3 daily for discovery; run Mode 4 on the shortlist of roles you want to apply to.

### Combining flags

```bash
# Monday morning after a 3-day weekend, global scope, free mode
python run.py --no-tailor --offline-classify --hours 72 --all-locations

# Only FPGA-specific search today
python run.py --no-tailor --keywords "FPGA,HDL,Vivado,Quartus"

# Custom output folder (useful for archiving)
python run.py --no-tailor --out ~/Desktop/applications/2026-08-13/
```

---

## Output files

Every run writes to `jobs_YYYY-MM-DD/` (or `--out` path):

```
jobs_2026-08-13/
├── INDEX.md                        ← Full list grouped by region (Bay Area first)
├── run.log                         ← Per-source fetch status + counts for debugging
├── nvidia__gpu-verification-engineer-new-college-grad.md
├── intel__rtl-design-engineer.md
└── ...                             ← One .md per qualifying job
```

Each per-job file contains:
- Company, title, location, age, source, apply link
- Tailored resume projects (or a note that generation was skipped)
- First 2000 chars of the job description

---

## Company coverage

### Confirmed 100% working

These were live-probed during setup — API returned 200 with real job data.

| Company | Method | Notes |
|---|---|---|
| **Intel** | Workday direct | 249 matching jobs in probe |
| **NVIDIA** | Workday direct | 669 jobs in probe; appeared in first run |
| **Micron** | Workday direct | 425 jobs in probe |
| **Marvell** | Workday direct | 12 jobs in probe |
| **Analog Devices** | Workday direct | 248 jobs in probe |
| **NXP Semiconductors** | Workday direct | 236 jobs in probe; appeared in first run |
| **AMD** | iCIMS direct (careers.amd.com/api/jobs) | 505 total jobs; 7 matching on test |
| **Tenstorrent** | Greenhouse | Appeared in first real run with 3 jobs |

### Expected to work — handles set, but not individually probed

Greenhouse API protocol is public and well-documented. If a handle is wrong you get a 404 (logged in `run.log`). These handles are correct to the best of knowledge but weren't live-tested — check `run.log` after your next run to confirm.

| Company | Method |
|---|---|
| Rivos | Greenhouse |
| Groq | Greenhouse |
| Cerebras | Greenhouse |
| SambaNova Systems | Greenhouse |
| Astera Labs | Greenhouse |
| Lightmatter | Greenhouse |
| d-Matrix | Greenhouse |
| Positron | Greenhouse |
| Etched | Greenhouse |
| Rain AI | Greenhouse |
| Silicon Labs | Greenhouse |
| Achronix | Greenhouse |
| Efinix | Greenhouse |
| Mythic | Greenhouse |
| Ampere | Lever |
| Nuvia (Qualcomm subsidiary) | Lever |

### Via aggregators — depends on what's indexed on LinkedIn / Google Jobs that day

These companies can't be scraped directly (bot-protected portals, custom ATS, or wrong Workday slug). Jobs surface through JSearch (LinkedIn/Indeed), SerpAPI (Google Jobs), and Adzuna. If a company posts a role and it's indexed within 24 hours, it will appear. Most major companies are indexed same-day; smaller ones may take 24–48h.

| Company | ATS (why direct fails) | Aggregator used |
|---|---|---|
| **Apple** | Custom portal (bot-protected) | SerpAPI targeted |
| **Google** | Custom portal (retired API) | SerpAPI targeted |
| **Qualcomm** | Eightfold AI (403 on all paths) | SerpAPI targeted |
| **Broadcom** | Likely SAP SuccessFactors (unconfirmed) | JSearch targeted |
| **Texas Instruments** | Oracle Talent Management | JSearch targeted |
| **Microchip Technology** | Unknown (403 on probe) | JSearch targeted |
| **Renesas** | Workday (wrong site slug — 422) | Adzuna targeted |
| **Infineon** | Unknown (DNS unreachable in probe) | Adzuna targeted |
| **Samsung Semiconductor** | — | Adzuna targeted |
| **MediaTek** | — | Adzuna targeted |
| **Arm** | — | Adzuna targeted |
| **Cadence** | — | Adzuna targeted |
| **Synopsys** | — | Adzuna targeted |
| **Lattice Semiconductor** | — | Adzuna targeted |
| **Skyworks** | — | Adzuna targeted |
| **Qorvo** | — | Adzuna generic only |
| **Silicon Labs** | Greenhouse (see above) + Adzuna generic | — |

> **Tip:** If a specific company keeps not showing up and you know they're hiring, open their careers page in Chrome → DevTools → Network → filter "jobs" → trigger a search → copy the POST URL → paste it into `companies.yaml` under `workday:` and the direct fetcher will pick it up.

### Not covered / unknown

Companies on iCIMS (other than AMD), Phenom People, SmartRecruiters, or heavily JS-guarded portals that weren't in scope. They may appear via generic aggregator queries if they post to LinkedIn/Indeed.

---

## API credit usage per run

### Anthropic (Claude)

| Model | Used for | Tokens per call | Cost per call | Calls per run | Est. cost per run |
|---|---|---|---|---|---|
| **Haiku 4.5** | Seniority classification | ~850 in / 5 out | ~$0.0007 | 20–50 borderline titles | **$0.01–0.04** |
| **Sonnet 4.6** | Project bullet generation | ~2200 in / 1200 out | ~$0.025 | 1 per qualifying job (5–20) | **$0.12–0.50** |

- Haiku pricing: $0.80 / MTok input · $4 / MTok output
- Sonnet pricing: $3 / MTok input · $15 / MTok output
- **Full run total: ~$0.15–0.55**
- **`--no-tailor` only (Haiku): ~$0.01–0.04**
- **`--offline-classify` or `--no-classify`: $0.00**

### SerpAPI (Google Jobs)

| Plan | Searches included | Price |
|---|---|---|
| Free | 100 / month | $0 |
| Hobby | 1,000 / month | ~$50/month |

**This tool uses: 3 calls per daily run = 90 calls/month** — stays inside free tier for daily use.

### JSearch (RapidAPI)

| Plan | Requests included | Price |
|---|---|---|
| Free (Basic) | 200 / month | $0 |
| Pro | 1,000 / month | ~$10/month |

**This tool uses: 6 calls per daily run = 180 calls/month** — stays inside free tier for daily use.

### Adzuna

| Plan | Calls included | Price |
|---|---|---|
| Free | 1,000 / month | $0 |

**This tool uses: 8 keyword + 10 overflow = 18 calls per daily run = 540 calls/month** — well inside free tier.

### Summary

| Scenario | Anthropic | SerpAPI | JSearch | Adzuna | Total / run |
|---|---|---|---|---|---|
| `--no-tailor --no-classify` | $0 | $0 | $0 | $0 | **$0** |
| `--no-tailor --offline-classify` | $0 | $0 | $0 | $0 | **$0** |
| `--no-tailor` | ~$0.01–0.04 | $0 | $0 | $0 | **~$0.01–0.04** |
| Full `python run.py` | ~$0.15–0.55 | $0 | $0 | $0 | **~$0.15–0.55** |

> SerpAPI, JSearch, and Adzuna are all $0 for daily use within the free tiers. The only meaningful cost is Anthropic, and only when you use Claude classification or tailoring.

---

## Debugging

- **Which sources fired and how many jobs each returned:** open `jobs_YYYY-MM-DD/run.log`.
- **A Greenhouse/Lever/Ashby handle returning 0 jobs:** either no new postings that day (normal) or the handle is wrong. Test directly: `curl https://boards-api.greenhouse.io/v1/boards/{handle}/jobs | python3 -m json.tool | head -20`.
- **Workday returning 422:** the `site` slug in the URL is wrong. Fix via DevTools (see README).
- **SerpAPI / JSearch returning 0:** free tier may be exhausted for the month. Check your dashboard.
- **Seniority filter keeping too many/too few roles:** in `--no-tailor` mode, edit the system prompt in `jobhunt/filters.py` → `_llm_classify`. In `--offline-classify` mode, adjust the YoE cutoff in `_offline_qualifies` (currently `<= 5`).
