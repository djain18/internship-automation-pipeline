from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlsplit

import requests

from models import Record, canonical_url, clean_text, iso_date


SEARCH_ENDPOINT = "https://api.firecrawl.dev/v1/search"
GENERIC_COMPANY_TOKENS = {
    "labs", "technologies", "technology", "solutions", "company", "private",
    "limited", "india",
}
EXCLUDED_DOMAINS = {"internshala.com", "naukri.com", "linkedin.com"}

# Aggregators and news outlets never ARE the company's own website, even when
# a search result about the company points at one. Rejecting these outright
# keeps resolve_company_url_via_search from ever "resolving" a company to a
# news article about it.
AGGREGATOR_DOMAINS = {
    "inc42.com", "yourstory.com", "entrackr.com", "crunchbase.com",
    "tracxn.com", "medium.com", "wikipedia.org", "x.com", "twitter.com",
    "facebook.com", "linkedin.com", "glassdoor.com", "youtube.com",
    "instagram.com", "reddit.com",
}


def _registrable_domain(url: str) -> str:
    host = urlsplit(url).netloc.casefold()
    return host[4:] if host.startswith("www.") else host


def _results(payload: Any) -> list[Record]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, dict):
        rows = data.get("web") or data.get("results") or data.get("data") or []
    else:
        rows = data
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def _relevant_to_company(company: str, title: str, text: str, url: str) -> bool:
    del text
    haystack = f"{title} {url}".casefold()
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", company.casefold())
        if len(token) >= 4 and token not in GENERIC_COMPANY_TOKENS
    ]
    return bool(tokens) and any(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)


def search_public_evidence(
    company: str,
    api_key: str,
    timeout: int = 45,
    limit_per_query: int = 3,
) -> list[Record]:
    # 2026-09-13: cut to one query and dropped scrapeOptions (each scraped
    # page adds ~1 credit on top of the 2-credit search itself) -- this now
    # feeds research_deep_problem for a small, capped set of companies
    # (max_deep_research_per_run) rather than every admitted internship, so
    # cost needs to stay tight against the free plan's 1,000 monthly
    # credits. "operations growth launch interview" targets how a company
    # runs, not review/pricing copy, which the Kimi instruction downstream
    # already can't use to support a hypothesis anyway.
    queries = [f'"{company}" operations growth launch interview']
    evidence: dict[str, Record] = {}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for query in queries:
        response = requests.post(
            SEARCH_ENDPOINT,
            headers=headers,
            json={"query": query, "limit": limit_per_query},
            timeout=timeout,
        )
        if response.status_code in {401, 403, 429}:
            raise RuntimeError(
                f"Firecrawl search unavailable with HTTP {response.status_code}; "
                "do not bypass or retry aggressively"
            )
        response.raise_for_status()
        for item in _results(response.json()):
            url = canonical_url(item.get("url"))
            if not url or any(domain in url.casefold() for domain in EXCLUDED_DOMAINS):
                continue
            title = clean_text(item.get("title") or url)
            text = clean_text(
                item.get("description") or item.get("markdown") or item.get("content")
            )[:700]
            if not text or not _relevant_to_company(company, title, text, url):
                continue
            evidence.setdefault(
                url,
                {
                    "type": "public_company_research",
                    # Must match the vocabulary problem_research.py's Kimi
                    # instruction actually checks (basis, not type) -- this
                    # was previously written but never wired to a caller, so
                    # the mismatch was never exercised.
                    "basis": "public_company_research",
                    "title": title,
                    "url": url,
                    "date": clean_text(item.get("publishedDate") or iso_date()),
                    "observation": text,
                    "confidence": "low",
                },
            )
    return list(evidence.values())[:5]


def _company_name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def resolve_company_url_via_search(
    company: str,
    api_key: str,
    timeout: int = 45,
) -> Record | None:
    """Resolve a funded company's real website with provenance, or return None.

    Never guesses a domain from a name. A domain is only ever accepted from a
    live Firecrawl search result AND only after fetching that exact candidate
    page and confirming the company's own name actually appears on it --
    company_resolve.py's existing exact-name-match pools stay the only other
    source of a company_url; this is a third pool, not a replacement, and it
    still requires the company's name to physically be on the resolved page.
    """
    from company_site import fetch_site_evidence

    company = clean_text(company)
    if not company:
        return None
    name_key = _company_name_key(company)
    if not name_key:
        return None

    queries = [f'"{company}" official website', f'"{company}" funding Bengaluru']
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    candidates: dict[str, dict[str, Any]] = {}
    for query in queries:
        response = requests.post(
            SEARCH_ENDPOINT,
            headers=headers,
            json={"query": query, "limit": 3},
            timeout=timeout,
        )
        if response.status_code in {401, 403, 429}:
            raise RuntimeError(
                f"Firecrawl search unavailable with HTTP {response.status_code}; "
                "do not bypass or retry aggressively"
            )
        response.raise_for_status()
        for item in _results(response.json()):
            url = canonical_url(item.get("url"))
            if not url:
                continue
            domain = _registrable_domain(url)
            if not domain or domain in EXCLUDED_DOMAINS or domain in AGGREGATOR_DOMAINS:
                continue
            if any(domain.endswith(f".{agg}") for agg in AGGREGATOR_DOMAINS):
                continue
            title = clean_text(item.get("title") or url)
            if not _relevant_to_company(company, title, "", url):
                continue
            entry = candidates.setdefault(
                domain, {"url": url, "query": query, "title": title, "queries": set()}
            )
            entry["queries"].add(query)

    if not candidates:
        return None

    # Verify each candidate live before accepting any of them -- a search
    # result naming the company is not proof the domain IS the company's
    # site; the candidate's own page must actually say so.
    for domain, info in candidates.items():
        candidate_url = f"https://{domain}"
        try:
            evidence, _emails, _linkedin, status = fetch_site_evidence(candidate_url)
        except Exception:
            continue
        if status != "ok":
            continue
        joined = _company_name_key(
            " ".join(item.get("observation", "") for item in evidence)
        )
        if name_key not in joined:
            continue
        agreeing = len(info["queries"])
        return {
            "company_url": candidate_url,
            "company_url_basis": "firecrawl_search_verified_onpage_name",
            "company_url_evidence": {
                "search_query": info["query"],
                "result_url": info["url"],
                "matched_text": next(
                    (
                        item.get("observation", "")
                        for item in evidence
                        if name_key in _company_name_key(item.get("observation", ""))
                    ),
                    "",
                ),
                "access_date": iso_date(),
                "confidence": "high" if agreeing > 1 else "medium",
            },
        }
    return None


def maybe_add_firecrawl_evidence(record: Record) -> tuple[Record, str]:
    provider = os.getenv("PUBLIC_RESEARCH_PROVIDER", "source_evidence").casefold()
    if provider != "firecrawl":
        return record, "source_evidence_free"
    enabled = os.getenv("ENABLE_FIRECRAWL_RESEARCH", "").casefold() in {
        "1", "true", "yes",
    }
    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not enabled:
        return record, "disabled"
    if not api_key:
        return record, "missing_api_key"
    copy = dict(record)
    existing = list(record.get("evidence") or [])
    try:
        discovered = search_public_evidence(str(record.get("company", "")), api_key)
    except Exception as exc:
        copy["research_fetch_error"] = str(exc)[:300]
        return copy, "failed"
    seen = {canonical_url(item.get("url")) for item in existing if isinstance(item, dict)}
    copy["evidence"] = existing + [
        item for item in discovered if canonical_url(item.get("url")) not in seen
    ]
    return copy, "ok"

