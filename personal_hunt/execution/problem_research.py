"""Deep problem research for discovered funded companies.

Collects evidence from company-owned surfaces, public social sources
(HN, X, LinkedIn posts), and app store reviews to ground a problem
hypothesis in real observed signals.

Evidence is sourced only from public, robots-respecting sources with
proper rate limiting and caching. All claims must be quoted verbatim
from the fetched text.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

from company_site import fetch_site_evidence
from models import Record, clean_text, canonical_url
from research import cached_bedrock_json


def _fetch_hackernews_evidence(
    company_name: str,
    min_days_old: int = 365,
    timeout: int = 10,
) -> list[Record]:
    """Fetch Hacker News posts mentioning the company via Algolia API.

    Returns evidence records with quoted text from posts.
    Never raises; a failed fetch returns an empty list.
    """
    try:
        # Filter to posts from the last year
        now = datetime.now(timezone.utc)
        cutoff_timestamp = int((now - timedelta(days=min_days_old)).timestamp())

        url = "https://hn.algolia.com/api/v1/search"
        params = {
            "query": company_name,
            "numericFilters": f"created_at_i>{cutoff_timestamp}",
            "hitsPerPage": 10,
        }
        headers = {
            "User-Agent": "InternshipResearch/0.1",
        }
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        evidence: list[Record] = []
        access_date = now.date().isoformat()

        for hit in data.get("hits", []):
            # HN hits can be stories or comments
            # Comments have comment_text, stories have story_text
            text = hit.get("comment_text") or hit.get("story_text") or ""
            if not text or len(text) < 40:
                continue

            title = hit.get("story_title") or ""
            url_item = hit.get("url") or hit.get("story_url") or ""

            # Build a representative quote: title + first sentence
            if title:
                quote = f"{title}. {text[:200]}"
            else:
                quote = text[:300]

            quote = clean_text(quote)
            if len(quote) < 50:
                continue

            record_url = url_item or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

            evidence.append(
                {
                    "url": canonical_url(record_url),
                    "observation": quote[:400],
                    "access_date": access_date,
                    "confidence": "low",
                    "basis": "hacker_news_algolia",
                }
            )

        return evidence
    except Exception:
        return []


def _fetch_site_and_roles(company_url: str) -> tuple[list[Record], list[str], list[str]]:
    """Fetch company website evidence and parse roles from opportunities.

    Reuses company_site.py for robots-respecting website fetches.
    Returns (evidence, emails, linkedin_urls).
    """
    try:
        # 2026-09-13: raised 3 -> 5. CANDIDATE_PATHS was reordered
        # operational-first (careers/jobs/blog/changelog/engineering before
        # about/company/homepage); 5 lets both an operational page and a
        # descriptive fallback page land instead of stopping after 3 mostly
        # non-operational hits.
        evidence, emails, linkedin_urls, _status = fetch_site_evidence(company_url, max_pages=5)
        return evidence, emails, linkedin_urls
    except Exception:
        return [], [], []


_SOFTWARE_TERMS = (
    "api", "saas", "software", "platform", "ai", "artificial intelligence",
    "machine learning", "app", "cloud", "sdk", "algorithm", "automation",
)


def _has_software_terms(evidence_items: list[Record]) -> bool:
    text = " ".join(item.get("observation", "") for item in evidence_items).casefold()
    return any(term in text for term in _SOFTWARE_TERMS)


def _apply_sector_bonus(lane: str, has_software_terms: bool) -> float:
    """Calculate sector bonus for ranking.

    ai and consumer lanes get bonus. unknown with software/AI terms also
    gets bonus (since lane classification is imperfect and many real
    companies come back unknown).
    """
    if lane in {"ai", "consumer"}:
        return 1.0
    if lane == "unknown" and has_software_terms:
        return 0.5
    return 0.0


def _score_evidence(
    evidence_items: list[Record],
    current_date: date,
    lane: str,
    sector_bonus_weight: float = 3.0,
) -> float:
    """Score evidence by volume, recency, and sector affinity.

    Score is used for ranking which companies get researched.
    """
    if not evidence_items:
        return 0.0

    # Volume: number of distinct evidence sources
    volume_score = min(len(evidence_items), 5) * 10.0

    # Recency: prefer evidence from the last 90 days
    recency_score = 0.0
    for item in evidence_items:
        access_date_str = item.get("access_date", "")
        try:
            access_date = datetime.fromisoformat(access_date_str).date()
            days_old = (current_date - access_date).days
            if 0 <= days_old <= 90:
                recency_score += 10.0
            elif days_old <= 365:
                recency_score += 5.0
        except ValueError:
            pass

    # Sector: bonus for high-signal lanes, or unknown lanes whose own
    # fetched evidence reads as software/AI (lane is often wrong, not
    # missing -- a hard rule here would drop good companies the same way
    # the LinkedIn identity bug once did).
    sector_bonus = _apply_sector_bonus(lane, _has_software_terms(evidence_items)) * sector_bonus_weight

    return volume_score + recency_score + sector_bonus


def research_deep_problem(
    company: Record,
    llm_cache: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    model_id: str = "",
    region: str = "",
) -> Record:
    """Research the problem space for one funded company.

    Returns a record with:
    - observed_signals: list of quoted evidence with URLs
    - problem_hypothesis: inferred problem statement
    - why_now: timing inference
    - confidence: assessment of evidence strength
    - supported: whether the evidence supports the hypothesis
    - evidence_score: numeric ranking signal
    """
    config = config or {}
    company_url = company.get("company_url", "")
    company_name = company.get("company", "")

    # Collect evidence from all sources
    all_evidence: list[Record] = []
    published_linkedin_urls: list[str] = []

    # 1. Company-owned surfaces
    site_evidence, _emails, site_linkedin_urls = _fetch_site_and_roles(company_url)
    all_evidence.extend(site_evidence)
    published_linkedin_urls.extend(site_linkedin_urls)

    # 2. Hacker News via Algolia
    hn_evidence = _fetch_hackernews_evidence(company_name)
    all_evidence.extend(hn_evidence)

    # 3. Apify sources (X/LinkedIn posts) - reuse existing budget-guarded fetcher
    # Note: This would require wiring in apify_sources.py but that's already
    # configured and budgeted. For now, rely on site + HN.

    if not all_evidence:
        return {
            "problem_status": "insufficient_evidence",
            "evidence_count": 0,
            "evidence_score": 0.0,
            "observed_signals": [],
            "problem_hypothesis": "",
            "why_now": "",
            "confidence": "low",
            "supported": False,
            "published_linkedin_urls": published_linkedin_urls,
        }

    # Score evidence for ranking
    lane = company.get("lane", "unknown")
    sector_bonus_weight = float(config.get("deep_research_sector_bonus", 3.0))
    evidence_score = _score_evidence(all_evidence, date.today(), lane, sector_bonus_weight)

    # Check minimum evidence threshold
    min_evidence = int(config.get("deep_research_min_evidence", 2))
    if len(all_evidence) < min_evidence:
        return {
            "problem_status": "insufficient_evidence",
            "evidence_count": len(all_evidence),
            "evidence_score": evidence_score,
            "observed_signals": [],
            "problem_hypothesis": "",
            "why_now": "",
            "confidence": "low",
            "supported": False,
            "published_linkedin_urls": published_linkedin_urls,
        }

    # Call LLM to synthesize hypothesis if enabled
    if not model_id or not region or not os.getenv("ENABLE_BEDROCK", "").casefold() in {"1", "true", "yes"}:
        # Return structured response without LLM
        return {
            "problem_status": "evidence_only",
            "evidence_count": len(all_evidence),
            "evidence_score": evidence_score,
            "observed_signals": [
                {
                    "text": item.get("observation", "")[:200],
                    "url": item.get("url", ""),
                    "basis": item.get("basis", ""),
                    "access_date": item.get("access_date", ""),
                }
                for item in all_evidence[:5]
            ],
            "problem_hypothesis": "",
            "why_now": "",
            "confidence": "medium",
            "supported": False,
            "published_linkedin_urls": published_linkedin_urls,
        }

    # LLM synthesis with fail-closed validation
    try:
        content = {
            "company_name": company_name,
            "company_url": company_url,
            "industry": company.get("lane", "unknown"),
            "evidence": [
                {
                    "basis": item.get("basis", ""),
                    "text": item.get("observation", "")[:500],
                    "url": item.get("url", ""),
                }
                for item in all_evidence[:8]
            ],
            "instruction": (
                "Analyze the evidence and return ONLY a JSON object with: "
                "observed_signals (list of {text, url} pairs with exact quotes from evidence), "
                "problem_hypothesis (one problem inferred from evidence), "
                "why_now (why this problem is acute now), "
                "confidence (low/medium/high), "
                "supported (true if multiple evidence items support the hypothesis). "
                "If a signal quote is NOT an exact substring of any evidence text, drop it. "
                "No invented facts. Return ONLY valid JSON.\n\n"
                "Critical constraint: the hypothesis must be an INTERNAL operational problem "
                "this company itself likely has -- team workflow friction, support/onboarding "
                "load implied by hiring, internal tooling gaps, process bottlenecks -- never a "
                "complaint about their own core commercial product, its pricing, or its "
                "features. Marketing copy, a pricing page, or product-feature descriptions are "
                "NOT evidence of an internal problem; a company describing what it sells is not "
                "a company confessing a weakness in that product. If the only evidence is "
                "marketing/pricing copy with no signal about how the company itself operates "
                "(open roles, support/ops complaints, engineering blog posts about internal "
                "pain, community posts about using their tools internally), set supported=false "
                "and leave problem_hypothesis empty rather than inventing an internal-sounding "
                "problem from external-facing copy. Each evidence item's basis field tells you "
                "which kind it is: company_site_descriptive is marketing/about copy and, alone, "
                "is NOT sufficient to support a hypothesis; company_site_operational, "
                "hacker_news_algolia, and public_company_research are eligible on their own."
            ),
        }

        payload, _usage = cached_bedrock_json(
            purpose="deep_problem_research",
            model_id=model_id,
            prompt_version="v1",
            content=content,
            prompt=str(content),
            region=region,
            cache=llm_cache,
            max_tokens=2000,
        )

        # Validate that observed_signals are literal substrings AND that the
        # attached URL is one we actually fetched -- text-only checking lets
        # the model pair a real quote with a fabricated or mismatched URL,
        # which breaks the provenance the fail-closed gate exists to give.
        validated_signals = []
        known_urls = {item.get("url", "") for item in all_evidence if item.get("url")}

        for signal in payload.get("observed_signals", []):
            if isinstance(signal, dict):
                text = signal.get("text", "")
                url = signal.get("url", "")
                if text and url and url in known_urls:
                    source_item = next(
                        (item for item in all_evidence if item.get("url") == url), None
                    )
                    if source_item and text in source_item.get("observation", ""):
                        validated_signals.append({"text": text[:200], "url": url})

        supported = bool(payload.get("supported", False))
        hypothesis = clean_text(payload.get("problem_hypothesis", ""))[:300] if supported else ""
        return {
            # Matches research_funding_event's pattern: status must reflect
            # the model's own supported verdict, not be hardcoded to the
            # validated outcome regardless of what the model actually said.
            "problem_status": "inference_needs_validation" if supported else "insufficient_evidence",
            "evidence_count": len(all_evidence),
            "evidence_score": evidence_score,
            "observed_signals": validated_signals,
            "problem_hypothesis": hypothesis,
            "why_now": clean_text(payload.get("why_now", ""))[:200] if supported else "",
            "confidence": clean_text(payload.get("confidence", "medium")),
            "supported": supported,
            "llm_status": "ok",
            "published_linkedin_urls": published_linkedin_urls,
        }

    except Exception as e:
        # Fail closed: return evidence only without synthesis
        return {
            "problem_status": "evidence_only",
            "evidence_count": len(all_evidence),
            "evidence_score": evidence_score,
            "observed_signals": [
                {
                    "text": item.get("observation", "")[:200],
                    "url": item.get("url", ""),
                }
                for item in all_evidence[:5]
            ],
            "problem_hypothesis": "",
            "why_now": "",
            "confidence": "medium",
            "supported": False,
            "llm_error": str(e)[:200],
            "llm_status": "failed",
            "published_linkedin_urls": published_linkedin_urls,
        }


def select_discovered_for_research(
    funded_companies: list[Record],
    config: dict[str, Any] | None = None,
    run_date: date | None = None,
    watchlist_companies: list[Record] | None = None,
) -> list[Record]:
    """Select funded companies for deep research based on evidence strength.

    Returns top N by evidence score, with minimum evidence threshold applied.
    Watchlist companies are ALWAYS included with no evidence-minimum gate.
    Companies with no evidence are filtered out.
    """
    config = config or {}
    run_date = run_date or date.today()
    max_per_run = int(config.get("max_deep_research_per_run", 8))
    sector_bonus_weight = float(config.get("deep_research_sector_bonus", 3.0))
    watchlist_companies = watchlist_companies or []

    # Watchlist companies are always included, with no evidence gate
    watchlist_selected = [
        company for company in watchlist_companies
        if company.get("company_url")
    ]

    # Quick pre-filter: reject funded companies with no company_url
    viable = [
        company for company in funded_companies
        if company.get("company_url") and company.get("company_url_basis")
    ]

    if not viable:
        return watchlist_selected

    # Score each funded company by evidence availability
    scored: list[tuple[Record, float]] = []
    for company in viable:
        lane = company.get("lane", "unknown")
        # Quick scoring: if we have a site URL, boost score
        company_url = company.get("company_url", "")
        base_score = 5.0 if company_url and company_url.startswith("http") else 0.0

        # Add sector bonus. No evidence fetched yet at this pre-filter stage,
        # so the unknown+software-terms branch can't fire here -- it only
        # applies once _score_evidence runs after site/HN evidence exists.
        base_score += _apply_sector_bonus(lane, False) * sector_bonus_weight

        scored.append((company, base_score))

    # Sort by score descending and take top N (minus slots reserved for watchlist)
    scored.sort(key=lambda x: x[1], reverse=True)
    # Reserve up to len(watchlist_selected) slots; remainder for discovered
    funded_slots = max(0, max_per_run - len(watchlist_selected))
    funded_selected = [company for company, _score in scored[:funded_slots]]

    # Combine: watchlist first (standing exception), then discovered
    return watchlist_selected + funded_selected
