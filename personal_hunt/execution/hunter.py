"""Hunter.io contact finder behind free-tier caps and a monthly domain cache.

Only fills gaps: records with no usable email get one bounded domain search.
Hunter results are found leads, never verified ones. Confidence reads high
only after a deliverable verification plus a strong score; a guessed or
pattern-derived address is never exposed as a contact.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import requests

from contacts import _mailbox_kind
from models import Record, canonical_url, clean_text


HUNTER_API = "https://api.hunter.io/v2"
REQUEST_TIMEOUT = 20

# Company sites only. Aggregators and inboxes cannot yield an employer address.
BLOCKED_HOSTS = {
    "linkedin.com",
    "www.linkedin.com",
    "lnkd.in",
    "wellfound.com",
    "www.wellfound.com",
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
}

LEADERSHIP_TERMS = (
    "founder",
    "co-founder",
    "cofounder",
    "ceo",
    "cto",
    "coo",
    "chief",
    "head",
    "president",
    "partner",
    "director",
    "vp ",
    "vice president",
    "owner",
)


def company_domain(record: Record) -> str:
    """Extract a searchable employer domain, or "" when there is none."""
    host = (urlsplit(clean_text(record.get("company_url"))).hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or host in BLOCKED_HOSTS:
        return ""
    return host


def account_quota(key: str) -> tuple[int, int] | None:
    """Free /account call: (searches available, verifications available)."""
    response = requests.get(
        f"{HUNTER_API}/account", params={"api_key": key}, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    requests_block = (response.json().get("data") or {}).get("requests") or {}
    searches = requests_block.get("searches") or {}
    verifications = requests_block.get("verifications") or {}
    return (int(searches.get("available", 0) or 0), int(verifications.get("available", 0) or 0))


def _is_leader(item: Record) -> bool:
    text = f"{item.get('position', '')} {item.get('seniority', '')} {item.get('department', '')}".casefold()
    return any(term in text for term in LEADERSHIP_TERMS)


def _pick(emails: list[Record], min_confidence: int) -> Record | None:
    """Best named personal address; leadership first, then confidence."""
    ranked = []
    for item in emails:
        if not isinstance(item, dict):
            continue
        email = clean_text(item.get("value"))
        if not email or _mailbox_kind(email) == "excluded":
            continue
        if clean_text(item.get("type")) != "personal":
            continue
        try:
            confidence = int(item.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            continue
        if confidence < min_confidence:
            continue
        if not clean_text(item.get("first_name")) and not clean_text(item.get("last_name")):
            continue
        sources = [s for s in (item.get("sources") or []) if isinstance(s, dict) and s.get("uri")]
        ranked.append((0 if _is_leader(item) else 1, -confidence, -len(sources), item))
    if not ranked:
        return None
    return sorted(ranked, key=lambda row: row[:3])[0][3]


def domain_search(key: str, domain: str, limit: int) -> tuple[list[Record], bool]:
    response = requests.get(
        f"{HUNTER_API}/domain-search",
        params={"domain": domain, "api_key": key, "limit": max(1, limit), "type": "personal"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json().get("data") or {}
    emails = data.get("emails") or []
    return ([item for item in emails if isinstance(item, dict)], bool(data.get("accept_all")))


def verify_email(key: str, email: str) -> Record:
    response = requests.get(
        f"{HUNTER_API}/email-verifier",
        params={"email": email, "api_key": key},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get("data") or {}


def _contact_from_pick(
    pick: Record, record: Record, accept_all: bool, verified: Record | None
) -> Record:
    email = clean_text(pick.get("value"))
    name = clean_text(f"{pick.get('first_name', '')} {pick.get('last_name', '')}".strip())
    sources = [
        clean_text(item.get("uri"))
        for item in (pick.get("sources") or [])
        if isinstance(item, dict) and item.get("uri")
    ][:3]
    hunter_score = pick.get("confidence", 0)
    status = "hunter_found_unverified"
    confidence = "medium" if sources else "low"
    if verified is not None:
        try:
            verify_score = int(verified.get("score", 0) or 0)
        except (TypeError, ValueError):
            verify_score = 0
        if (
            clean_text(verified.get("result")) == "deliverable"
            and verify_score >= 90
            and not accept_all
        ):
            status = "hunter_verified_deliverable"
            confidence = "high"
    return {
        "status": "available",
        "name": name,
        "role": clean_text(pick.get("position") or "hiring contact"),
        "email": email,
        "linkedin": "",
        "source_url": sources[0] if sources else canonical_source(record),
        "access_date": record.get("discovered_at") or record.get("access_date"),
        "verification_status": status,
        "basis": "hunter_domain_search",
        "confidence": confidence,
        "contact_priority": "preferred_named" if name else "unverified_lead",
        "hunter_confidence": hunter_score,
        "hunter_sources": sources,
    }


def canonical_source(record: Record) -> str:
    return canonical_url(record.get("company_url")) or canonical_url(record.get("source_url"))


def find_company_contact(
    record: Record, scoring: dict[str, Any], state: Any, month: str
) -> Record | None:
    """One bounded Hunter lookup for a contact-less record. Never raises."""
    try:
        return _find_company_contact(record, scoring, state, month)
    except Exception:
        return None


def _find_company_contact(
    record: Record, scoring: dict[str, Any], state: Any, month: str
) -> Record | None:
    if not scoring.get("hunter_enabled", True):
        return None
    key = os.getenv("HUNTER_API_KEY", "")
    if not key:
        return None
    domain = company_domain(record)
    if not domain:
        return None
    cached = state.hunter_domain_cache(month, domain)
    if cached is not None:
        if not cached.get("found"):
            return None
        return _contact_from_cached(cached, record)
    use = state.hunter_month_use(month)
    if use["searches"] >= int(scoring.get("hunter_monthly_max_searches", 25)):
        return None
    quota = account_quota(key)
    if quota is not None and quota[0] <= 0:
        return None
    emails, accept_all = domain_search(key, domain, int(scoring.get("hunter_limit_per_domain", 10)))
    state.record_hunter_use(month, "searches")
    pick = _pick(emails, int(scoring.get("hunter_min_confidence", 80)))
    if pick is None:
        state.cache_hunter_domain(month, domain, {"found": False})
        return None
    verified: Record | None = None
    if scoring.get("hunter_verify", False):
        use = state.hunter_month_use(month)
        max_verifications = int(scoring.get("hunter_monthly_max_verifications", 0) or 0)
        if max_verifications > 0 and use["verifications"] < max_verifications:
            if quota is None or quota[1] > 0:
                verified = verify_email(key, clean_text(pick.get("value")))
                state.record_hunter_use(month, "verifications")
    contact = _contact_from_pick(pick, record, accept_all, verified)
    state.cache_hunter_domain(
        month,
        domain,
        {
            "found": True,
            "email": contact["email"],
            "name": contact["name"],
            "role": contact["role"],
            "sources": contact["hunter_sources"],
            "hunter_confidence": contact["hunter_confidence"],
            "verification_status": contact["verification_status"],
            "confidence": contact["confidence"],
        },
    )
    return contact


def _contact_from_cached(cached: Record, record: Record) -> Record:
    return {
        "status": "available",
        "name": cached.get("name", ""),
        "role": cached.get("role", "hiring contact"),
        "email": cached.get("email", ""),
        "linkedin": "",
        "source_url": (cached.get("sources") or [canonical_source(record)])[0],
        "access_date": record.get("discovered_at") or record.get("access_date"),
        "verification_status": cached.get("verification_status", "hunter_found_unverified"),
        "basis": "hunter_domain_search",
        "confidence": cached.get("confidence", "low"),
        "contact_priority": "preferred_named" if cached.get("name") else "unverified_lead",
        "hunter_confidence": cached.get("hunter_confidence", 0),
        "hunter_sources": cached.get("sources", []),
        "cache_hit": True,
    }
