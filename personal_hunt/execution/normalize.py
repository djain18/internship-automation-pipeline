from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

from models import Record, canonical_url, clean_text, iso_date, stable_id


# An internship signal read out of a description, rather than a title. Bare
# "intern"/"fellow" is deliberately NOT enough: real postings say "your fellow
# new colleagues", "3+ years post-internship", "help junior teammates or
# interns", and German prose uses "intern" to mean internally. So the signal is
# either an unambiguous noun, or "<role family> intern", which reads like a job
# title and rescues postings whose title is truncated or misspelled.
INTERNSHIP_DESCRIPTION_SIGNAL = re.compile(
    r"(?<!post-)\b(internship|internships|apprenticeship|apprenticeships|"
    r"fellowship|fellowships|industrial trainee|summer trainee)\b"
    r"|\b(?:founder\'?s?|office|operations|ops|growth|business|product|marketing|"
    r"strategy|generalist|program|programme|project|research|summer|campus)"
    r"\s+intern\b"
)


def _terms(config: dict[str, Any], key: str) -> list[str]:
    return [str(item).casefold() for item in config.get(key, [])]


def _contains(text: str, terms: list[str]) -> bool:
    return any(
        bool(re.search(rf"\b{re.escape(term)}\b", text)) if len(term) <= 3 else term in text
        for term in terms
    )


def _first(record: Record, *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return ""


def _parse_employee_count(record: Record) -> int | None:
    direct = _first(record, "employee_count", "employees", "company_size")
    if isinstance(direct, int):
        return direct
    text = clean_text(direct).replace(",", "")
    if not text:
        return None
    numbers = [int(value) for value in re.findall(r"\d+", text)]
    if not numbers:
        return None
    return max(numbers) if len(numbers) > 1 else numbers[0]


def _parse_date(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text


def _parse_source_date(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        try:
            return parsedate_to_datetime(text).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return ""


def _is_linkedin_url(value: str) -> bool:
    host = urlsplit(value).netloc.casefold()
    return host == "lnkd.in" or host.endswith(".linkedin.com") or host == "linkedin.com"


def _parse_duration_months(record: Record) -> int | None:
    direct = record.get("duration_months")
    if isinstance(direct, int):
        return direct
    text = clean_text(direct or record.get("duration")).casefold()
    if not text:
        return None
    match = re.search(r"(\d+)\s*(?:month|months|mo)\b", text)
    return int(match.group(1)) if match else None


def classify_location(location: str, work_mode_hint: str = "") -> tuple[str, str]:
    text = f"{location} {work_mode_hint}".casefold()
    bengaluru = any(term in text for term in ("bengaluru", "bangalore"))
    remote = any(term in text for term in ("remote", "work from home", "wfh"))
    hybrid = "hybrid" in text
    onsite = any(term in text for term in ("onsite", "on-site", "in office", "office"))
    india_scope = any(
        term in text for term in ("india", "asia", "worldwide", "anywhere", "global")
    )

    if bengaluru:
        if hybrid:
            return "bengaluru_hybrid", "hybrid"
        if remote and not onsite:
            return "bengaluru_hybrid", "hybrid"
        return "bengaluru_onsite", "onsite"
    if remote and india_scope:
        return "india_remote", "remote"
    return "other", "unknown"


def classify_lane(text: str, roles: dict[str, Any], explicit: str = "") -> str:
    explicit_value = clean_text(explicit).casefold()
    if explicit_value in {"ai", "consumer"}:
        return explicit_value
    lowered = text.casefold()
    ai_score = sum(_contains(lowered, [term]) for term in _terms(roles, "ai_terms"))
    consumer_score = sum(
        _contains(lowered, [term]) for term in _terms(roles, "consumer_terms")
    )
    if ai_score == consumer_score == 0:
        return "unknown"
    return "ai" if ai_score >= consumer_score else "consumer"


def normalize_record(
    raw: Record,
    roles: dict[str, Any],
    scoring: dict[str, Any],
    discovered_at: str | None = None,
    first_seen_by_id: dict[str, str] | None = None,
) -> Record:
    source = clean_text(_first(raw, "source", "_source_id", "source_name")).casefold()
    company = clean_text(
        _first(raw, "company", "hiringOrganization", "organization", "company_name")
    )
    title = clean_text(_first(raw, "title", "position", "role"))
    description = clean_text(_first(raw, "description", "summary", "content"))
    location = clean_text(_first(raw, "location", "job_location"))
    source_url = canonical_url(_first(raw, "source_url", "_source_url", "link", "url"))
    apply_url = canonical_url(_first(raw, "apply_url", "link", "application_url", "url"))
    company_url = canonical_url(_first(raw, "company_url", "website"))
    location_class, work_mode = classify_location(
        location, clean_text(_first(raw, "work_mode", "type"))
    )
    joined = f"{company} {title} {description}"
    lane = classify_lane(joined, roles, clean_text(raw.get("lane")))
    employee_count = _parse_employee_count(raw)
    contact = raw.get("contact") if isinstance(raw.get("contact"), dict) else {}
    if not contact and any(raw.get(key) for key in ("hiringManager", "hiringManagerEmail")):
        contact = {
            "name": clean_text(raw.get("hiringManager")),
            "role": "hiring manager",
            "email": clean_text(raw.get("hiringManagerEmail")),
            "linkedin": canonical_url(raw.get("hiringManagerLinkedin")),
            "source_url": source_url,
            "verification_status": "published_by_source",
        }
    source_id = clean_text(_first(raw, "source_id", "id", "external_id"))
    opportunity_id = stable_id(source, source_id or apply_url or source_url, company, title)
    access_date = discovered_at or iso_date()
    first_discovered_at = clean_text(
        (first_seen_by_id or {}).get(opportunity_id) or raw.get("first_discovered_at")
    ) or access_date
    posted_raw = _first(
        raw,
        "posted_at",
        "posted_date",
        "published",
        "publishedAt",
        "createdAt",
        "created_at",
        "updatedAt",
    )
    parsed_posted_date = _parse_source_date(posted_raw)
    date_warnings: list[str] = []
    if posted_raw and not parsed_posted_date:
        date_warnings.append("invalid_source_posted_date_used_first_discovery")
    if parsed_posted_date:
        try:
            if datetime.fromisoformat(parsed_posted_date).date() > datetime.fromisoformat(
                access_date
            ).date():
                date_warnings.append("future_source_posted_date_used_first_discovery")
                parsed_posted_date = ""
        except ValueError:
            parsed_posted_date = ""
    linked_url = _is_linkedin_url(source_url) or _is_linkedin_url(apply_url)
    approved_linkedin = source in {"linkedin_posts_apify", "rise_public_sheet"}
    approved_x = source == "x_posts_apify"
    confidence = clean_text(raw.get("source_confidence") or "medium").casefold()
    verification = clean_text(
        raw.get("verification_status") or "machine_collected"
    ).casefold()
    if approved_linkedin or approved_x or (linked_url and verification != "human_verified"):
        confidence = "low"
        verification = "machine_collected_unverified"
    normalized: Record = {
        "id": opportunity_id,
        "source_id": source_id,
        "source": source,
        "source_url": source_url,
        "apply_url": apply_url,
        "company_url": company_url,
        "company": company,
        "title": title,
        "description": description,
        "location": location,
        "location_class": location_class,
        "work_mode": work_mode,
        "lane": lane,
        "employee_count": employee_count,
        "funding_date": _parse_date(raw.get("funding_date")),
        "funding_source_url": canonical_url(raw.get("funding_source_url")),
        "growth_signal": clean_text(raw.get("growth_signal")),
        "duration_months": _parse_duration_months(raw),
        "employment_type": clean_text(
            _first(raw, "employment_type", "employmentType", "timing")
        ),
        "deadline": _parse_date(raw.get("deadline")),
        "is_active": raw.get("isActive", raw.get("is_active", True)),
        "prospect_lane": clean_text(raw.get("prospect_lane") or "open_role").casefold(),
        "contact": contact,
        "evidence": list(raw.get("evidence") or []),
        "posted_date": parsed_posted_date or first_discovered_at,
        "posted_date_basis": (
            "source_posted_date" if parsed_posted_date else "first_discovered_at"
        ),
        "first_discovered_at": first_discovered_at,
        "discovered_at": access_date,
        "source_confidence": confidence,
        "verification_status": verification,
        "source_priority": int(raw.get("source_priority", 99) or 99),
        "date_warnings": date_warnings,
        "rejection_reasons": [],
    }
    normalized["rejection_reasons"] = hard_exclusions(normalized, roles, scoring)
    normalized["eligible"] = not normalized["rejection_reasons"]
    return normalized


def hard_exclusions(
    record: Record, roles: dict[str, Any], scoring: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    source = str(record.get("source", "")).casefold()
    title = str(record.get("title", "")).casefold()
    description = str(record.get("description", "")).casefold()
    joined = f"{title} {description}"

    if any(term in source for term in ("internshala", "naukri", "linkedin_jobs")):
        reasons.append("excluded_source")
    linked_url = _is_linkedin_url(str(record.get("source_url", ""))) or _is_linkedin_url(
        str(record.get("apply_url", ""))
    )
    approved_linkedin = source in {"linkedin_posts_apify", "rise_public_sheet"}
    if (
        ("linkedin" in source or linked_url)
        and not approved_linkedin
        and record.get("verification_status") != "human_verified"
    ):
        reasons.append("linkedin_post_requires_manual_verification")
    if record.get("is_active") is False:
        reasons.append("inactive_opportunity")
    count = record.get("employee_count")
    if isinstance(count, int) and count > int(scoring.get("max_employees", 400)):
        reasons.append("company_above_400_employees")
    duration = record.get("duration_months")
    minimum_months = int(scoring.get("min_duration_months", 2))
    maximum_months = int(scoring.get("max_duration_months", 12))
    if isinstance(duration, int) and not minimum_months <= duration <= maximum_months:
        reasons.append("duration_outside_target_window")
    internship_text = f"{title} {record.get('employment_type', '')}".casefold()
    is_internship = any(term in internship_text for term in ("intern", "fellow"))
    if not is_internship:
        is_internship = bool(INTERNSHIP_DESCRIPTION_SIGNAL.search(description))
    if record.get("prospect_lane") == "open_role" and not is_internship:
        reasons.append("not_internship_or_fellowship")
    deadline = clean_text(record.get("deadline"))
    discovered = clean_text(record.get("discovered_at"))
    try:
        if deadline and discovered and datetime.fromisoformat(deadline).date() < datetime.fromisoformat(discovered).date():
            reasons.append("application_deadline_passed")
    except ValueError:
        pass
    posted_date = clean_text(record.get("posted_date"))
    try:
        if posted_date and discovered:
            age_days = (
                datetime.fromisoformat(discovered).date()
                - datetime.fromisoformat(posted_date).date()
            ).days
            if age_days > int(scoring.get("max_posting_age_days", 7)):
                reasons.append("posted_over_7_days")
    except ValueError:
        reasons.append("invalid_posted_date")
    if _contains(joined, _terms(roles, "senior_reject")):
        reasons.append("senior_role")
    accepted = _contains(joined, _terms(roles, "accepted")) or _contains(
        title, _terms(roles, "accepted_title")
    )
    cross_functional = _contains(joined, _terms(roles, "cross_functional_terms"))
    specialist = _contains(title, _terms(roles, "specialist_reject"))
    if specialist and not cross_functional:
        reasons.append("specialist_only_role")
    if not accepted and not cross_functional:
        reasons.append("role_not_cross_functional")
    if record.get("location_class") == "other":
        reasons.append("location_out_of_scope")
    if not record.get("company") or not record.get("title") or not record.get("source_url"):
        reasons.append("missing_required_identity_or_source")
    return sorted(set(reasons))


def normalize_many(
    records: list[Record],
    roles: dict[str, Any],
    scoring: dict[str, Any],
    discovered_at: str | None = None,
    first_seen_by_id: dict[str, str] | None = None,
) -> list[Record]:
    return [
        normalize_record(item, roles, scoring, discovered_at, first_seen_by_id)
        for item in records
    ]
