from __future__ import annotations

import os
import re
from typing import Any

import requests

from models import Record, canonical_url, clean_text, iso_date


SEARCH_ENDPOINT = "https://api.firecrawl.dev/v1/search"
GENERIC_COMPANY_TOKENS = {
    "labs", "technologies", "technology", "solutions", "company", "private",
    "limited", "india",
}
EXCLUDED_DOMAINS = {"internshala.com", "naukri.com", "linkedin.com"}


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
    queries = [
        f'"{company}" customer reviews complaints product',
        f'"{company}" operations growth launch interview',
    ]
    evidence: dict[str, Record] = {}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for query in queries:
        response = requests.post(
            SEARCH_ENDPOINT,
            headers=headers,
            json={
                "query": query,
                "limit": limit_per_query,
                "scrapeOptions": {"formats": ["markdown"]},
            },
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
                    "title": title,
                    "url": url,
                    "date": clean_text(item.get("publishedDate") or iso_date()),
                    "observation": text,
                    "confidence": "low",
                },
            )
    return list(evidence.values())[:5]


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

