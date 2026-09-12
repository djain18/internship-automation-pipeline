from __future__ import annotations

from datetime import date, datetime
from typing import Any

from models import Record
from normalize import _contains, _terms


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _recent(date_text: str, run_date: date, max_days: int) -> bool:
    if not date_text:
        return False
    try:
        value = datetime.fromisoformat(date_text).date()
    except ValueError:
        return False
    return 0 <= (run_date - value).days <= max_days


def score_record(
    record: Record,
    roles: dict[str, Any],
    scoring: dict[str, Any],
    run_date: date,
) -> Record:
    if not record.get("eligible"):
        record["score"] = 0
        record["score_components"] = {}
        record["score_reasons"] = ["hard_exclusion"]
        return record

    weights = scoring["weights"]
    joined = f"{record.get('title', '')} {record.get('description', '')}".casefold()
    components: dict[str, int] = {}
    reasons: list[str] = []

    location_class = record.get("location_class")
    components["location"] = {
        "bengaluru_onsite": weights["location"],
        "bengaluru_hybrid": weights["location"],
        "india_remote": weights["location"] // 2,
    }.get(location_class, 0)
    reasons.append(f"location:{location_class}")

    accepted = _contains_any(joined, roles.get("accepted", []))
    cross = _contains_any(joined, roles.get("cross_functional_terms", []))
    # A named role family in the TITLE is as explicit as the curated phrases in
    # `accepted`: "Business Development Intern" is the same shape as the listed
    # "growth intern", and requiring it in the title is positionally stricter.
    title_family = _contains(
        str(record.get("title", "")).casefold(), _terms(roles, "accepted_title")
    )
    # A record admitted by the Tier 2 description read scores as a
    # cross-functional signal, not an explicit match: Kimi judged the breadth of
    # the work, not that the title names a target role family. Without this the
    # record clears hard_exclusions and then dies at publish_threshold, which
    # would make the whole Tier 2 judgement decorative.
    judged = record.get("role_fit_basis") == "llm_cross_functional_judgement"
    if accepted or title_family:
        components["role_breadth"] = weights["role_breadth"]
    else:
        components["role_breadth"] = 14 if (cross or judged) else 0
    if accepted:
        reasons.append("role:explicit_match")
    elif title_family:
        reasons.append("role:title_family_match")
    elif judged:
        reasons.append("role:llm_cross_functional_judgement")
    else:
        reasons.append("role:cross_functional_signal")

    lane = record.get("lane")
    components["lane_fit"] = weights["lane_fit"] if lane in {"ai", "consumer"} else 0
    reasons.append(f"lane:{lane}")

    candidate_terms = [
        "founder", "operations", "automation", "growth", "gtm", "strategy",
        "special projects", "generalist", "d2c", "retail",
        "chief of staff", "fundraise", "fundraising", "analytics",
    ]
    components["candidate_fit"] = (
        weights["candidate_fit"] if _contains_any(joined, candidate_terms) else 6
    )

    count = record.get("employee_count")
    if isinstance(count, int) and count <= int(scoring["preferred_max_employees"]):
        components["company_size"] = weights["company_size"]
        reasons.append("size:preferred")
    elif isinstance(count, int) and count <= int(scoring["max_employees"]):
        components["company_size"] = weights["company_size"] // 2
        reasons.append("size:accepted_with_penalty")
    else:
        components["company_size"] = 4
        reasons.append("size:unverified")

    if _recent(
        str(record.get("funding_date", "")),
        run_date,
        int(scoring["funding_recency_days"]),
    ):
        components["funding_growth"] = weights["funding_growth"]
        reasons.append("signal:recent_funding")
    elif record.get("growth_signal"):
        components["funding_growth"] = 7
        reasons.append("signal:growth")
    else:
        components["funding_growth"] = 2
        reasons.append("signal:weak_or_unverified")

    founder_exposure = _contains_any(
        joined, ["founder", "cross-functional", "special projects", "zero to one", "0 to 1"]
    )
    components["learning"] = weights["learning"] if founder_exposure else 2

    confidence_points = {
        "official": 4,
        "high": 4,
        "medium": 3,
        "low": 1,
        "unverified": 0,
    }.get(str(record.get("source_confidence", "")).casefold(), 1)
    contact_bonus = 1 if record.get("contact") else 0
    components["source_contact"] = min(
        weights["source_contact"], confidence_points + contact_bonus
    )

    record["score_components"] = components
    record["score"] = sum(components.values())
    threshold = int(scoring["publish_threshold"])
    # An exactly-named target role in Bengaluru publishes on title and location
    # alone. Without this floor it structurally cannot: 46 of the 100 points
    # (lane_fit 15, company_size 10, funding_growth 10, learning 5, source
    # contact 5) measure company metadata that is unverifiable for the small
    # unknown startups Daksh is actually hunting, so a perfect match maxing
    # location (20), role_breadth (20) and candidate_fit (15) tops out at 64
    # against a threshold of 70. Two real Bengaluru internships on
    # run_f9ae04eb99b98d0e — Shobitam "Partnerships Growth Intern" (Jayanagar,
    # posted 2026-09-10) and Vatsenix "Business Development Intern"
    # (Whitefield) — both scored exactly 64 and were dropped as
    # below_publish_threshold. Daksh 2026-09-13: "I just want a founder's
    # office internship, or a growth internship — such generalist roles... I
    # will take care of the JD myself." The floor never invents a fact: it
    # applies only where the title already matched a curated role phrase or
    # title family AND the location is a verified Bengaluru class. Kimi's
    # independent llm_fit_threshold read still gates what reaches the digest.
    if (accepted or title_family) and location_class in {
        "bengaluru_onsite",
        "bengaluru_hybrid",
    }:
        record["score"] = max(record["score"], threshold)
        reasons.append("floor:named_role_in_bengaluru")
    record["score_reasons"] = reasons
    record["eligible"] = record["score"] >= threshold
    if not record["eligible"]:
        record["rejection_reasons"] = sorted(
            set(record.get("rejection_reasons", []) + ["below_publish_threshold"])
        )
    return record


def score_many(
    records: list[Record],
    roles: dict[str, Any],
    scoring: dict[str, Any],
    run_date: date,
) -> list[Record]:
    return [score_record(item, roles, scoring, run_date) for item in records]


def select_balanced(records: list[Record], scoring: dict[str, Any]) -> dict[str, list[Record]]:
    eligible = [item for item in records if item.get("eligible")]
    primary = sorted(
        [
            item for item in eligible
            if item.get("location_class") in {"bengaluru_onsite", "bengaluru_hybrid"}
        ],
        key=lambda item: (
            -int(item.get("score", 0)),
            int(item.get("source_priority", 99)),
            item["id"],
        ),
    )
    fallback = sorted(
        [item for item in eligible if item.get("location_class") == "india_remote"],
        key=lambda item: (
            -int(item.get("score", 0)),
            int(item.get("source_priority", 99)),
            item["id"],
        ),
    )
    # llm_shortlist_size is how many eligible records reach the Kimi gate;
    # daily_target stays a separate, smaller number used only for the
    # digest's "X of target Y" reporting text (digest.py), never for
    # slicing the actual candidate pool. Falls back to daily_target when
    # unset so older configs/tests keep working.
    target = int(scoring.get("llm_shortlist_size", scoring["daily_target"]))
    quotas = scoring.get("lane_quota", {"ai": 3, "consumer": 3})
    selected: list[Record] = []
    used: set[str] = set()
    for lane in ("ai", "consumer"):
        lane_items = [item for item in primary if item.get("lane") == lane]
        for item in lane_items[: int(quotas.get(lane, 0))]:
            selected.append(item)
            used.add(item["id"])
    for item in primary:
        if len(selected) >= target:
            break
        if item["id"] not in used:
            selected.append(item)
            used.add(item["id"])
    selected.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            int(item.get("source_priority", 99)),
            item["id"],
        )
    )
    return {"primary": selected[:target], "remote_fallback": fallback[:target]}

