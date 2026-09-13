"""Generate paste-ready Claude Code prompts for researched companies.

Each prompt specifies a runnable prototype scoped to a few hours,
grounded in observed problems and the company's visible tech stack.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from models import Record, clean_text
from research import cached_bedrock_json


PROMPT_TEMPLATE = """{company_name}: {problem_brief}

## Problem

{observed_problem}

Evidence:
{evidence_urls}

## What to build

A single runnable prototype, scoped to {scope_hours} hours.

{what_to_build}

## Stack constraint

{stack_constraint}

## Acceptance criteria

{acceptance_criteria}

## Instructions

Do not invent facts about {company_name}. Mark every assumption in the README.
Build and test locally; do not make external API calls beyond reading this brief."""


_CLONE_TERMS = ("clone", "alternative", "competitor", "version of", "rebuild")
# Must match templates/prototype_prompt.txt's real headings, not the embedded
# PROMPT_TEMPLATE fallback -- _load_prompt_template() prefers the disk file
# when it exists, and it does in this repo, so validating against the
# fallback's different wording ("## Problem", "## What to build") would
# reject every prompt this pipeline actually generates.
_REQUIRED_SECTIONS = ("## Observed signals", "## Build the prototype", "## Acceptance criteria")


def validate_prototype_prompt(prompt_text: str, company_name: str) -> list[str]:
    """Structural checks build_prototype_prompt's own LLM call has no way to
    enforce on itself -- unlike outreach, which has validate_outreach, this
    generator previously had nothing between "the LLM returned JSON" and
    "the digest prints it." Returns an empty list when the prompt is fine."""
    errors: list[str] = []
    text = prompt_text or ""
    if len(text) < 400:
        errors.append("prompt shorter than 400 characters")
        return errors
    for section in _REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"missing required section: {section}")
    # A bare unresolved {word} is what str.format() leaves behind on a
    # missing template key.
    if re.search(r"\{[a-z_]+\}", text):
        errors.append("unresolved template placeholder left in prompt")
    if not re.search(r"https?://", text):
        errors.append("no evidence URL present in prompt body")
    name = clean_text(company_name)
    if name:
        lowered = text.casefold()
        name_lower = name.casefold()
        for term in _CLONE_TERMS:
            idx = lowered.find(name_lower)
            while idx != -1:
                window = lowered[max(0, idx - 40): idx + len(name_lower) + 40]
                if term in window:
                    errors.append(f"prompt reads as a clone/competitor of {company_name}")
                    break
                idx = lowered.find(name_lower, idx + 1)
            else:
                continue
            break
    return errors


def load_prompt_template(filename: str, fallback: str, templates_dir: Path | None = None) -> str:
    """Load a template from templates/ by filename, falling back to an
    embedded default when the file is missing or unreadable. Shared with
    outreach.py's build_email_prompt so a missing template file degrades
    instead of crashing, the same guarantee this module already gives
    prototype_prompt.txt."""
    if templates_dir is None:
        templates_dir = Path(__file__).parent.parent / "templates"

    template_file = templates_dir / filename
    if template_file.exists():
        try:
            return template_file.read_text("utf-8").strip()
        except Exception:
            pass
    return fallback


def _load_prompt_template(templates_dir: Path | None = None) -> str:
    """prototype_prompt.txt specifically. See load_prompt_template."""
    return load_prompt_template("prototype_prompt.txt", PROMPT_TEMPLATE, templates_dir)


def build_prototype_prompt(
    company: Record,
    problem_research: Record | None = None,
    llm_cache: dict[str, Any] | None = None,
    model_id: str = "",
    region: str = "",
) -> Record:
    """Generate a paste-ready Claude Code prompt for a researched company.

    Returns a record with:
    - prompt_text: the full prompt
    - prompt_basis: brief description of evidence quality
    - evidence_urls: list of URLs used to ground the prompt
    - llm_status: ok, skipped, failed
    """
    company_name = company.get("company", "")
    company_url = company.get("company_url", "")
    problem_research = problem_research or {}

    # Gather evidence URLs
    evidence_urls = []
    for signal in problem_research.get("observed_signals", []):
        url = signal.get("url", "")
        if url:
            evidence_urls.append(url)

    if not company_name or not evidence_urls:
        return {
            "prompt_text": "",
            "prompt_basis": "insufficient_evidence",
            "evidence_urls": [],
            "llm_status": "skipped_no_evidence",
        }

    # 2026-09-13: a real cloud run showed this generating "Build an internal
    # vendor cookie audit dashboard for Lyzr AI's marketing/ops team" from
    # evidence that was literally a cookie-consent banner -- observed_signals
    # can be non-empty (a real quote from a real page) while
    # research_deep_problem still correctly judged supported=false and left
    # problem_hypothesis empty, because a quote merely being real doesn't
    # make it evidence of an internal PROBLEM. Requiring evidence_urls alone
    # let this function invent a prototype anyway. Same fail-closed pattern
    # research_funding_event already uses for its own allow_llm gate.
    if not problem_research.get("supported") or not clean_text(
        problem_research.get("problem_hypothesis", "")
    ):
        return {
            "prompt_text": "",
            "prompt_basis": f"{len(evidence_urls)}_urls_unsupported_hypothesis",
            "evidence_urls": evidence_urls,
            "llm_status": "skipped_unsupported_hypothesis",
        }

    # Check if LLM is enabled and configured
    if not model_id or not region or not os.getenv("ENABLE_BEDROCK", "").casefold() in {"1", "true", "yes"}:
        return {
            "prompt_text": "",
            "prompt_basis": f"{len(evidence_urls)}_urls_no_llm",
            "evidence_urls": evidence_urls,
            "llm_status": "skipped_disabled",
        }

    # Call LLM to generate prompt
    try:
        problem_hypothesis = problem_research.get("problem_hypothesis", "")
        signals = problem_research.get("observed_signals", [])

        observed_problem = "Problem hypothesis: " + problem_hypothesis if problem_hypothesis else ""
        if signals:
            observed_problem += "\n\nObserved signals:\n"
            for signal in signals[:5]:
                observed_problem += f"- {signal.get('text', '')}\n"

        content = {
            "company_name": company_name,
            "problem_hypothesis": problem_hypothesis,
            "evidence_count": len(evidence_urls),
            "company_url": company_url,
            "instruction": (
                "Generate a Claude Code prompt for building a runnable prototype. "
                "The prompt must include: (1) the problem, (2) what to build in a few hours, "
                "(3) tech stack based on what the company uses, (4) file layout and fake data, "
                "(5) screen-recordable acceptance criteria, (6) explicit warning not to invent facts. "
                "Return ONLY a JSON object with: what_to_build (paragraph), stack_constraint (paragraph), "
                "acceptance_criteria (list), scope_hours (number). "
                "Do not invent company tech stack; mark assumptions as assumptions.\n\n"
                "Critical constraint: the prototype must NEVER be a clone, competitor, or "
                "reimplementation of the company's own core commercial product or anything on "
                "its pricing page -- a candidate showing up with a cut-rate copy of the thing "
                "the company sells for money is not a pitch, it is an insult. Build something "
                "ADJACENT that would plausibly help the company's own internal team do their "
                "job better: an internal ops dashboard, a support/onboarding workflow tool, a "
                "monitoring or triage aid, a process automation -- grounded in the stated "
                "problem_hypothesis, which is itself already constrained to be an internal "
                "operational problem, not a product complaint. If what_to_build would end up "
                "re-describing the company's own product or pricing tiers, that is a sign the "
                "hypothesis was not actually internal -- build something narrower and internal "
                "instead, even a small one."
            ),
            "observed_problem": observed_problem[:1000],
        }

        payload, _usage = cached_bedrock_json(
            purpose="build_prototype_prompt",
            model_id=model_id,
            prompt_version="v1",
            content=content,
            prompt=str(content),
            region=region,
            cache=llm_cache,
            max_tokens=2000,
        )

        # Build the prompt from template and LLM response
        template = _load_prompt_template()

        what_to_build = clean_text(payload.get("what_to_build", ""))[:800]
        stack_constraint = clean_text(payload.get("stack_constraint", ""))[:500]
        scope_hours = int(payload.get("scope_hours", 4))

        acceptance_items = payload.get("acceptance_criteria", [])
        if isinstance(acceptance_items, list):
            acceptance_criteria = "\n".join(
                f"- {clean_text(str(item))}"
                for item in acceptance_items[:5]
            )
        else:
            acceptance_criteria = "- [Generated acceptance criteria not available]"

        evidence_urls_text = "\n".join(f"- {url}" for url in evidence_urls[:5])

        prompt_text = template.format(
            company_name=company_name,
            problem_brief=problem_hypothesis[:100] if problem_hypothesis else "Unknown",
            observed_problem=observed_problem,
            evidence_urls=evidence_urls_text,
            scope_hours=scope_hours,
            what_to_build=what_to_build,
            stack_constraint=stack_constraint,
            acceptance_criteria=acceptance_criteria,
        )

        validation_errors = validate_prototype_prompt(prompt_text, company_name)
        if validation_errors:
            # Fail closed like every other quality gate here: a prompt that
            # fails structural validation (too short, missing a required
            # section, no evidence URL, or reads as a clone/competitor -- the
            # same failure class as the Emergent bug, caught here structurally
            # instead of by someone reading the email) never reaches Daksh.
            return {
                "prompt_text": "",
                "prompt_basis": f"{len(evidence_urls)}_urls_blocked_validation",
                "evidence_urls": evidence_urls,
                "llm_status": "blocked_validation",
                "validation_errors": validation_errors,
            }

        return {
            "prompt_text": prompt_text,
            "prompt_basis": f"{len(evidence_urls)}_urls_llm_generated",
            "evidence_urls": evidence_urls,
            "llm_status": "ok",
            "scope_hours": scope_hours,
            # Separate from prompt_text so outreach.py can say what the
            # prototype does in one line, without re-parsing the assembled
            # prompt to find it.
            "what_to_build": what_to_build,
        }

    except Exception as e:
        # Fail closed: return no prompt
        return {
            "prompt_text": "",
            "prompt_basis": f"{len(evidence_urls)}_urls_llm_failed",
            "evidence_urls": evidence_urls,
            "llm_status": "failed",
            "llm_error": str(e)[:200],
        }


def build_prompts_for_companies(
    companies: list[Record],
    llm_cache: dict[str, Any] | None = None,
    model_id: str = "",
    region: str = "",
) -> list[Record]:
    """Generate prompts for all researched companies.

    Returns list of company records with prompt_text and prompt_basis added.
    """
    output = []
    for company in companies:
        # Phase 2 writes its result to "deep_problem_research". Funding
        # events also carry a "problem_research" key from Phase 1's
        # research_funding_event, which is a different, unrelated shape
        # (no observed_signals list) -- reading it here would silently
        # never find evidence.
        problem_research = company.get("deep_problem_research", {})
        prompt_result = build_prototype_prompt(
            company,
            problem_research,
            llm_cache,
            model_id,
            region,
        )

        enriched = dict(company)
        enriched["prompt_generation"] = prompt_result
        output.append(enriched)

    return output
