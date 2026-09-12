from __future__ import annotations

import re

from models import Record, clean_text


# Multi-company roundup headlines name a whole week's worth of raises, not
# one company. _company_from_title's regex still matches the first name in
# the sentence (e.g. "Pixxel" out of "From Pixxel To Swish — Indian
# Startups Raised Over $321.9 Mn This Week"), which is wrong: the article
# is not about Pixxel specifically, and treating it as a Pixxel funding
# event would misattribute the whole roundup's evidence to one company.
# Verified against live Inc42/YourStory feeds on 2026-09-13 before writing
# this: real single-company articles never match these patterns; real
# roundups always do.
_ROUNDUP_PATTERNS = (
    re.compile(r"\bthis week\b", re.I),
    re.compile(r"\bfunding roundup\b", re.I),
    re.compile(r"\bweekly funding\b", re.I),
    re.compile(r"\bstartups?\s+raised\b", re.I),
    re.compile(r"^\s*from\s+.+\s+to\s+.+", re.I),
    re.compile(r"\[\s*weekly", re.I),
)


def is_roundup_headline(title: str) -> bool:
    """True when a headline is a multi-company weekly/period summary
    rather than a report about one funding event."""
    text = clean_text(title)
    if not text:
        return False
    return any(pattern.search(text) for pattern in _ROUNDUP_PATTERNS)


def _company_key(value: object) -> str:
    return "".join(character for character in clean_text(value).casefold() if character.isalnum())


def _match_company_url(records: list[Record], pool: list[Record], basis: str) -> list[Record]:
    """Attach company_url only on one exact, unambiguous name match against
    `pool`. Mirrors pipeline.attach_company_provenance's matching rule; kept
    as a separate, small implementation here (rather than imported) so this
    module and pipeline.py can import each other without a cycle -- this
    file is imported by pipeline.py before funding events reach the LLM
    research step."""
    matches: dict[str, list[Record]] = {}
    for candidate in pool:
        key = _company_key(candidate.get("company"))
        if key and candidate.get("company_url"):
            matches.setdefault(key, []).append(candidate)
    output: list[Record] = []
    for record in records:
        item = dict(record)
        if item.get("company_url"):
            output.append(item)
            continue
        found = matches.get(_company_key(item.get("company")), [])
        if len(found) == 1:
            item["company_url"] = found[0]["company_url"]
            item["company_url_basis"] = basis
        output.append(item)
    return output


def resolve_company_urls(
    events: list[Record],
    registry_companies: list[Record],
    run_opportunities: list[Record],
) -> list[Record]:
    """Attach a real company_url to a funding event, or label it honestly.

    Two legitimate sources only, both exact casefolded-name matches against
    records that already carry a real, non-guessed company_url:
    1. reviewed VC-portfolio registries (discover_companies.fetch_registries)
    2. this run's own normalized opportunities, whose company_url was
       resolved from their own apply-link host
       (normalize._company_url_from_links) -- a company that is both
       hiring and freshly funded in the same run resolves for free.

    An earlier draft of this assumed the funding article's own body links
    out to the company's site; three live Inc42/YourStory articles fetched
    on 2026-09-13, including the exact roundup this run rejects, showed
    that assumption was false -- articles link to the outlet's own other
    articles or nothing. No new fetch is added here as a result.

    No domain is ever guessed from a company name. An event that matches
    neither pool is returned with company_url_basis: unresolved and no
    company_url; Phase 2's evidence-volume ranking naturally sends it to
    the bottom rather than treating it specially here.
    """
    resolved = _match_company_url(
        events, registry_companies, "reviewed_registry_exact_company_name"
    )
    resolved = _match_company_url(
        resolved, run_opportunities, "same_run_opportunity_exact_company_name"
    )
    output: list[Record] = []
    for event in resolved:
        item = dict(event)
        if not item.get("company_url"):
            item["company_url_basis"] = "unresolved"
        output.append(item)
    return output
