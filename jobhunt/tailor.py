"""Uses Claude Sonnet 4.6 to generate 2-3 tailored resume projects per JD.

Reads resume_context.txt so the model sees the candidate's real experience and
education and can write projects that complement (not duplicate) them.
"""
from __future__ import annotations
from pathlib import Path

from .llm import client, SONNET
from .models import Job

_SYSTEM = """You write resume PROJECT section entries that will make a hiring manager immediately want to interview the candidate for a SPECIFIC job.

Rules — follow ALL of them:
1. Output EXACTLY 2 or 3 projects. No more, no fewer.
2. Each project must directly match the job description's technical asks — echo the JD's exact keywords (protocols, tools, methodologies) in the bullets.
3. Each project must be REALISTIC for a Masters student with 2+ yrs SoC RTL verification experience to actually build in 4-8 weeks. NO fake industry projects, NO "led a team", NO fake scale numbers, NO invented company names.
4. Projects must NOT duplicate what's already in the candidate's Experience section. They should complement it (e.g. if candidate did AXI verification at ARM, don't propose another AXI project — propose something adjacent like CHI or DDR).
5. Each project = 1 title line + 3-4 tight resume bullets (each bullet <= 25 words, quantified where honest, action-verb start).
6. Use domain-authentic verbs and stack: SystemVerilog, UVM, coverage-driven, constrained-random, formal, scoreboard, reference model, RAL, VCS/Questa/Xcelium, Verdi, gtkwave, cocotb, Yosys, OpenLane, iVerilog, Vivado, Quartus, Cadence Xcelium.
7. Metrics must be plausible (e.g. "achieved 100% functional coverage", "cut regression runtime from 6h→45m") — NOT round marketing numbers.
8. Output plain markdown. No preamble, no explanation, no closing summary. Just the project entries.

Format each project exactly like:

**<Project Title> — <Year or Duration>**
- <bullet 1>
- <bullet 2>
- <bullet 3>
- <optional bullet 4>
"""

_RESUME_PATH = Path(__file__).resolve().parent.parent / "resume_context.txt"
_RESUME_CACHE: str | None = None


def _resume() -> str:
    global _RESUME_CACHE
    if _RESUME_CACHE is None:
        _RESUME_CACHE = _RESUME_PATH.read_text(encoding="utf-8")
    return _RESUME_CACHE


def tailor_projects(job: Job) -> str:
    user = (
        f"CANDIDATE RESUME CONTEXT (experience + education are fixed, do not repeat them in projects):\n"
        f"{'-' * 60}\n{_resume()}\n{'-' * 60}\n\n"
        f"TARGET JOB:\n"
        f"Company: {job.company}\n"
        f"Title:   {job.title}\n"
        f"Location: {job.location}\n\n"
        f"JOB DESCRIPTION (may be truncated):\n{job.description[:3000] or '(no description available — infer from title)'}\n\n"
        f"Write 2-3 resume PROJECT entries that will make a recruiter for THIS role want to interview the candidate. "
        f"Follow every rule in the system prompt exactly."
    )
    msg = client().messages.create(
        model=SONNET,
        max_tokens=1200,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
