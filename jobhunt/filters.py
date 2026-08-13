"""Keyword + date filters (fast) + two-stage seniority filter (regex then LLM)."""
from __future__ import annotations
import concurrent.futures
import re
from datetime import datetime, timedelta, timezone

from .llm import client, HAIKU
from .models import Job

# Hard-exclude: people-management, executive, and clearly senior-IC titles that
# the user does NOT qualify for. Everything else (including Senior, Architect,
# Staff, Principal) falls through to the LLM classifier so title+JD together
# decide.
HARD_EXCLUDE_RE = re.compile(
    r"\b("
    r"director|vp|vice\s*president|head\s+of|chief|c[toei]o|"
    r"people\s+manager|engineering\s+manager|"
    r"manager,|manager\b(?!\s+of\s+one)|"  # "Manager, X" or "Manager"
    r"fellow|distinguished"
    r")\b",
    re.IGNORECASE,
)

# Titles that don't need LLM at all — clearly entry/mid IC.
CLEAR_KEEP_RE = re.compile(
    r"\b("
    r"new\s*grad|university\s*grad|associate|junior|entry[-\s]*level|"
    r"engineer\s+(?:i|ii|1|2)\b|"
    r"intern|co-?op"
    r")\b",
    re.IGNORECASE,
)


def keyword_filter(jobs: list[Job], keywords: list[str]) -> list[Job]:
    kws = [k.lower() for k in keywords]
    out = []
    for j in jobs:
        hay = f"{j.title}\n{j.description}".lower()
        if any(kw in hay for kw in kws):
            out.append(j)
    return out


# --- Location handling --------------------------------------------------------
# US state 2-letter abbreviations (used as \b-anchored regex, case-sensitive so
# "in" as a preposition doesn't match "IN" for Indiana).
_US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
_US_STATE_RE = re.compile(r"\b(" + "|".join(_US_STATES) + r")\b")

# Full state names (case-insensitive). Ordered longest-first so multi-word states
# match before their substrings if any ambiguity ever appears.
_US_STATE_FULL = [
    "california", "texas", "new york", "washington", "oregon", "colorado", "arizona",
    "florida", "georgia", "north carolina", "south carolina", "massachusetts",
    "pennsylvania", "new jersey", "new mexico", "new hampshire", "connecticut",
    "michigan", "minnesota", "wisconsin", "illinois", "indiana", "ohio", "iowa",
    "missouri", "tennessee", "kentucky", "virginia", "west virginia", "maryland",
    "delaware", "rhode island", "vermont", "maine", "alabama", "arkansas",
    "louisiana", "mississippi", "kansas", "nebraska", "south dakota", "north dakota",
    "montana", "wyoming", "idaho", "utah", "nevada", "oklahoma", "alaska", "hawaii",
]
_US_STATE_FULL_RE = re.compile(
    r"\b(" + "|".join(s.replace(" ", r"\s+") for s in _US_STATE_FULL) + r")\b",
    re.IGNORECASE,
)

_US_WORD_RE = re.compile(
    r"\b(united\s+states|usa|u\.s\.a?\.?|remote\s*[-,]\s*us|remote\s+usa?)\b",
    re.IGNORECASE,
)
_NON_US_HINT_RE = re.compile(
    r"\b(india|bengaluru|bangalore|hyderabad|noida|gurgaon|pune|chennai|mumbai|"
    r"china|shanghai|shenzhen|beijing|taipei|taiwan|"
    r"tokyo|japan|osaka|"
    r"korea|seoul|"
    r"singapore|malaysia|vietnam|thailand|philippines|indonesia|"
    r"germany|munich|berlin|dresden|"
    r"uk|london|manchester|edinburgh|dublin|ireland|"
    r"france|paris|grenoble|"
    r"israel|tel\s*aviv|haifa|"
    r"canada|toronto|ottawa|montreal|vancouver|"
    r"mexico|guadalajara|"
    r"brazil|australia|sydney|melbourne)\b",
    re.IGNORECASE,
)

# Bay Area cities in priority order — the FIRST match wins as the city label.
_BAY_AREA_CITIES: list[tuple[str, str]] = [
    ("San Jose",       r"san\s+jose"),
    ("San Francisco",  r"san\s+francisco|\bsf\b"),
    ("Santa Clara",    r"santa\s+clara"),
    ("Sunnyvale",      r"sunnyvale"),
    ("Mountain View",  r"mountain\s+view"),
    ("Palo Alto",      r"palo\s+alto"),
    ("Cupertino",      r"cupertino"),
    ("Fremont",        r"fremont"),
    ("Milpitas",       r"milpitas"),
    ("Menlo Park",     r"menlo\s+park"),
    ("Redwood City",   r"redwood\s+city"),
    ("Foster City",    r"foster\s+city"),
    ("San Mateo",      r"san\s+mateo"),
    ("Burlingame",     r"burlingame"),
    ("Newark",         r"newark,\s*ca"),
    ("Union City",     r"union\s+city"),
    ("Hayward",        r"hayward"),
    ("Oakland",        r"oakland"),
    ("Berkeley",       r"berkeley"),
    ("Emeryville",     r"emeryville"),
    ("Alameda",        r"alameda"),
    ("Pleasanton",     r"pleasanton"),
    ("Dublin",         r"dublin,\s*ca"),
    ("Bay Area",       r"bay\s+area"),  # last-resort fallback
]
_BAY_AREA_COMPILED = [(label, re.compile(pat, re.IGNORECASE)) for label, pat in _BAY_AREA_CITIES]
_BAY_AREA_RE = re.compile("|".join(pat for _, pat in _BAY_AREA_CITIES), re.IGNORECASE)


def bay_area_city(loc: str) -> str | None:
    if not loc:
        return None
    for label, pat in _BAY_AREA_COMPILED:
        if pat.search(loc):
            return label
    return None
_CALIFORNIA_RE = re.compile(r"\b(california|,\s*ca\b|\bca\s*$|\bca\s*,)", re.IGNORECASE)


def is_us_location(loc: str) -> bool:
    """Best-effort: keep obvious US locations, drop obvious non-US, keep unknowns."""
    if not loc or not loc.strip():
        return True  # unknown → keep, user can eyeball
    if _NON_US_HINT_RE.search(loc):
        # Non-US hint present. But if a US state is *also* present (e.g. multi-loc
        # posting "San Jose, CA; Bengaluru, India"), keep it.
        if _US_STATE_RE.search(loc) or _US_STATE_FULL_RE.search(loc) or _US_WORD_RE.search(loc):
            return True
        return False
    if _US_STATE_RE.search(loc):
        return True
    if _US_STATE_FULL_RE.search(loc):
        return True
    if _US_WORD_RE.search(loc):
        return True
    if re.search(r"\bremote\b", loc, re.IGNORECASE):
        # "Remote" with no country hint → assume US, keep
        return True
    return False


def location_priority(loc: str) -> int:
    """Lower = higher priority in the sorted table.
    0 = Bay Area, 1 = California (non-Bay), 2 = other US, 3 = unknown/remote."""
    if not loc:
        return 3
    if _BAY_AREA_RE.search(loc):
        return 0
    if _CALIFORNIA_RE.search(loc):
        return 1
    if _US_STATE_RE.search(loc) or _US_STATE_FULL_RE.search(loc) or _US_WORD_RE.search(loc):
        return 2
    return 3


def us_location_filter(jobs: list[Job]) -> list[Job]:
    return [j for j in jobs if is_us_location(j.location)]


# --- Recency ------------------------------------------------------------------

def recency_filter(jobs: list[Job], hours: int) -> list[Job]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out = []
    for j in jobs:
        if j.posted_at is None:
            # Unknown-age postings from ATSes without dates get kept; user can
            # eyeball them in the output.
            out.append(j)
            continue
        if j.posted_at >= cutoff:
            out.append(j)
    return out


def dedupe(jobs: list[Job]) -> list[Job]:
    seen: dict[str, Job] = {}
    for j in jobs:
        k = j.dedup_key()
        if k not in seen:
            seen[k] = j
        else:
            # Prefer the record with a description (better for downstream tailoring).
            if not seen[k].description and j.description:
                seen[k] = j
    return list(seen.values())


def _llm_classify(job: Job) -> bool:
    """Returns True if the role is plausibly suitable for 2-3 YoE.
    Uses Haiku with a strict schema so we can parse yes/no reliably."""
    system = (
        "You are screening whether a specific candidate should apply to a job. "
        "Candidate profile: 2+ years of SoC RTL verification at ARM, MS in Electrical Engineering in progress. "
        "They CAN apply to: new-grad, junior, mid-level, and Senior IC roles requiring up to ~5 YoE. "
        "They CAN also apply to Architect-titled roles that are individual-contributor and don't require 8+ YoE — "
        "many companies use 'Architect' in the title for mid-level IC positions (example: "
        "'Server SoC System Architect' at Qualcomm is a valid apply-to role for this candidate even though the "
        "title contains 'Architect'). Look at the JD's stated YoE requirement, not the title alone.\n\n"
        "They CANNOT apply to: Principal / Staff / Distinguished / Fellow roles that require 8+ YoE, "
        "any Manager / Director / VP / Head-of role that manages people, or roles that gate on a PhD.\n\n"
        "Decision rule: if the JD's YoE requirement is <=5 years AND the role is individual-contributor, say YES. "
        "If the JD says '8+ years' or 'must lead a team' or 'PhD required', say NO. "
        "If the JD is ambiguous, default to YES — better to over-include and let the human decide.\n\n"
        "Reply with EXACTLY one word: YES or NO."
    )
    prompt = (
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Description (first 1500 chars):\n{job.description[:1500]}\n\n"
        f"Should the candidate (2+ yrs SoC RTL verif, MS in progress) apply? Answer YES or NO only."
    )
    try:
        msg = client().messages.create(
            model=HAIKU,
            max_tokens=5,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip().upper()
        return text.startswith("Y")
    except Exception as e:
        print(f"  [classify:err] {job.company} {job.title[:40]}: {e}")
        return True  # fail open — better to over-include than lose a real role


def seniority_filter(jobs: list[Job]) -> list[Job]:
    kept: list[Job] = []
    to_llm: list[Job] = []
    for j in jobs:
        if HARD_EXCLUDE_RE.search(j.title):
            continue
        if CLEAR_KEEP_RE.search(j.title):
            kept.append(j)
            continue
        to_llm.append(j)

    if not to_llm:
        return kept

    print(f"  [classify] {len(to_llm)} borderline titles → Haiku")
    # Run in a thread pool since anthropic SDK's create() is blocking.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_llm_classify, to_llm))
    for job, ok in zip(to_llm, results):
        if ok:
            kept.append(job)
    return kept


# --- Offline classifier (no API needed) ---------------------------------------
# Extracts YoE requirement from JD text via regex. Rules:
#   - Hard-exclude titles (Manager/Director/etc) → drop
#   - Title in CLEAR_KEEP_RE → keep
#   - Otherwise scan JD for YoE mentions; keep if min-YoE <=5, drop if >5, keep if none
_YOE_MIN_RE = re.compile(
    r"(?:minimum\s+(?:of\s+)?|at\s+least\s+|>=\s*|\bmin\.?\s+)?(\d+)\+?\s*(?:\-\s*\d+\s*)?"
    r"\s*(?:years?|yrs?|yoe)\b[^.]{0,60}(?:experience|exp\b|professional)",
    re.IGNORECASE,
)
_PHD_RE = re.compile(
    r"\bph\.?\s*d\.?\b[^.]{0,80}\b(required|mandatory|must\s+have)\b|"
    r"\brequires?\s+a?\s*ph\.?\s*d\.?\b",
    re.IGNORECASE,
)
_LEAD_TEAM_RE = re.compile(r"\b(lead|manage|mentor)\s+a\s+team\b|\bmanage\s+direct\s+reports\b|\bhire\s+and\s+manage\b", re.IGNORECASE)


def _offline_qualifies(job: Job) -> bool:
    txt = job.description or ""
    if _PHD_RE.search(txt) or _LEAD_TEAM_RE.search(txt):
        return False
    yoes = [int(m.group(1)) for m in _YOE_MIN_RE.finditer(txt)]
    if not yoes:
        return True  # unknown → keep
    # If any YoE mention says 6+, drop
    return min(yoes) <= 5


def seniority_filter_offline(jobs: list[Job]) -> list[Job]:
    kept: list[Job] = []
    for j in jobs:
        if HARD_EXCLUDE_RE.search(j.title):
            continue
        if CLEAR_KEEP_RE.search(j.title):
            kept.append(j)
            continue
        if _offline_qualifies(j):
            kept.append(j)
    return kept
