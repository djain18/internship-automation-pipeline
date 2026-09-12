"""Generate paste-ready Claude Code prompts for researched companies.

Each prompt specifies a runnable prototype scoped to a few hours,
grounded in observed problems and the company's visible tech stack.
"""

from __future__ import annotations

import os
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


def _load_prompt_template(templates_dir: Path | None = None) -> str:
    """Load prompt template from templates/ directory if available."""
    if templates_dir is None:
        templates_dir = Path(__file__).parent.parent / "templates"

    template_file = templates_dir / "prototype_prompt.txt"
    if template_file.exists():
        try:
            return template_file.read_text("utf-8").strip()
        except Exception:
            pass

    # Fall back to embedded template
    return PROMPT_TEMPLATE


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
                "Do not invent company tech stack; mark assumptions as assumptions."
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

        return {
            "prompt_text": prompt_text,
            "prompt_basis": f"{len(evidence_urls)}_urls_llm_generated",
            "evidence_urls": evidence_urls,
            "llm_status": "ok",
            "scope_hours": scope_hours,
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
        problem_research = company.get("problem_research", {})
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
