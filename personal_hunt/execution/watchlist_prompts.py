"""One-shot deep-dive prompts for the fixed watchlist companies.

Deterministic. No network, no LLM call. Formats facts already verified and
recorded in config/watchlist.yml into a self-contained Claude Code prompt --
Daksh runs the research and drafts the email himself, in a fresh conversation,
using /humanizer. See config/watchlist.yml's deep_research flag: this module
is the replacement for running that research automatically every day.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# outreach.py's EMAIL_COPY_RULES already says it is "shared with
# watchlist_prompts.py ... so the copy rules Claude Code is told to follow are
# defined once, not retyped per feature and left to drift" -- a verbatim copy
# here was exactly the drift that comment forbids.
from outreach import (
    CANDIDATE_FACTS,
    EMAIL_AUDIT_STEPS,
    EMAIL_COPY_RULES,
    EMAIL_OUTPUT_FORMAT,
    FORBIDDEN_PHRASES,
    FORBIDDEN_WORDS,
    HUMANIZER_RULES,
)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def build_watchlist_prompt(company: dict[str, Any]) -> str:
    name = company.get("name", "")
    site_url = company.get("site_url", "")
    board_url = company.get("board_url", "")
    description = " ".join((company.get("description") or "").split())

    forbidden_words = ", ".join(FORBIDDEN_WORDS)
    forbidden_phrases = "; ".join(f'"{phrase}"' for phrase in FORBIDDEN_PHRASES)

    lines = [
        f"# {name}: deep-dive research + outreach draft",
        "",
        "## Verified ground (do not re-derive; do not contradict without new evidence)",
        "",
        f"- Company: {name}",
        f"- Site: {site_url}" if site_url else "- Site: not on file",
        f"- Careers/board URL: {board_url}" if board_url else "- Careers/board URL: not on file",
        f"- What is already known: {description}" if description else "- What is already known: nothing beyond the site URL.",
        "",
        "## Research brief",
        "",
        "Find ONE real, current, specific operational problem at this company that a",
        "six-month Founder's Office/generalist intern could plausibly help with. Read the",
        "site, the careers page, any engineering blog or changelog, and recent public",
        "posts by its founders. For every material claim, cite the source URL and the date",
        "you accessed it. Keep what you directly observed separate from what you are",
        "inferring. If you cannot find a real problem, say so plainly rather than inventing",
        "one -- \"not found\" is a valid, honest result.",
        "",
        "## Draft the outreach",
        "",
        "Once you have one source-backed problem and a small solution idea, draft:",
        "",
        "1. A cold email to a founder or relevant functional leader at this company.",
        "2. A LinkedIn connection note.",
        "",
        "About Daksh (verified; use one fact, the most relevant):",
        *CANDIDATE_FACTS,
        "",
        "What gets cold emails answered:",
        *(rule.replace("{resume_basename}", "Daksh-Jain-Master") for rule in EMAIL_COPY_RULES),
        "",
        "Humanizer rules (apply while writing, not only after):",
        *HUMANIZER_RULES,
        f"- Never use these words: {forbidden_words}.",
        f"- Never use these phrases: {forbidden_phrases}.",
        "- Never invent a metric, a familiarity, or an artifact that does not exist.",
        "- Never promise an unmeasured outcome or turn an inference into a stated fact.",
        "",
        "## Before you finish",
        "",
        *EMAIL_AUDIT_STEPS,
        "",
        *EMAIL_OUTPUT_FORMAT,
        "",
    ]
    return "\n".join(lines)


def write_watchlist_prompts(watchlist_config: dict[str, Any], output_dir: Path) -> list[Path]:
    """Write one prompt file per watchlist company. Returns the written paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for company in watchlist_config.get("companies", []):
        # Same guard watchlist_board_sources and _watchlist_to_companies use:
        # a non-dict entry in the YAML is skipped, not crashed on.
        if not isinstance(company, dict):
            continue
        name = company.get("name", "")
        if not name:
            continue
        path = output_dir / f"{_slug(name)}.md"
        path.write_text(build_watchlist_prompt(company), encoding="utf-8")
        written.append(path)
    return written
