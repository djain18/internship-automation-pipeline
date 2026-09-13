from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.hunt_core.links import validate_application_link
from execution.hunt_core.network import enable_system_ca

enable_system_ca()

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env", override=False)
except ImportError:
    pass

if os.getenv("AWS_BEDROCK") and not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = os.environ["AWS_BEDROCK"]
if os.getenv("ENABLE_BEDROCK", "").casefold() in {"1", "true", "yes"}:
    # Blank .env lines must not win over defaults: setdefault keeps empties.
    if not os.getenv("AWS_REGION", ""):
        os.environ["AWS_REGION"] = "ap-south-1"
    if not os.getenv("BEDROCK_RESEARCH_MODEL_ID", ""):
        os.environ["BEDROCK_RESEARCH_MODEL_ID"] = "moonshotai.kimi-k2.5"

from artifacts import create_artifacts
from build_prompt import build_prompts_for_companies
from config import AUTOMATION_ROOT, load_all
from company_resolve import resolve_company_urls
from company_site import fetch_office_evidence
from firecrawl_research import resolve_company_url_via_search
from contacts import attach_contact, choose_contact
from dedupe import deduplicate
from digest import render_digest, render_html_digest, send_self_digest, write_digest
from discover_companies import fetch_registries
from fetch_sources import (
    SPOTTED_FILE,
    SPOTTED_SOURCE_ID,
    fetch_live,
    fixture_health,
    load_json_records,
    load_spotted_leads,
    watchlist_board_sources,
)
from funding import fetch_funding_live, select_funding_events
from llm_rank import extract_linkedin_hiring_fields, judge_cross_functional, score_shortlist
from models import Record, clean_text, normalized_content_hash, stable_id, usage_summary, utc_timestamp
from normalize import normalize_many
from outreach import draft_outreach, validate_outreach
from problem_research import research_deep_problem, select_discovered_for_research
from watchlist_prompts import write_watchlist_prompts
from research import research_funding_event, research_records
from score import score_many, select_balanced
from sheets import publish_run
from state import LocalState


def route_resume(record: Record) -> str:
    title = str(record.get("title", "")).casefold()
    text = f"{title} {record.get('description', '')}".casefold()
    if any(
        term in title
        for term in ("founder", "chief of staff", "generalist", "special projects")
    ):
        return "Daksh-Jain-founders_office"
    if any(term in text for term in ("growth", "gtm", "go-to-market")):
        return "Daksh-Jain-gtm"
    if record.get("lane") == "ai" and any(
        term in text for term in ("automation", "ai", "llm")
    ):
        return "Daksh-Jain-ai_automation"
    if record.get("lane") == "consumer" or any(
        term in text for term in ("operations", "supply chain", "d2c", "retail")
    ):
        return "Daksh-Jain-ops"
    return "Daksh-Jain-Master"


def enrich_selected(
    records: list[Record],
    output_root: Path,
    max_artifacts: int,
    llm_cache: dict[str, Any] | None = None,
    hunter_ctx: dict[str, Any] | None = None,
) -> list[Record]:
    output = deepcopy(records)
    research_results = research_records(output, cache=llm_cache)
    for item, research in zip(output, research_results, strict=True):
        item["research"] = research
        item["selected_contact"] = attach_contact(item, hunter_ctx)
        item["resume"] = route_resume(item)
        item["content_hash"] = normalized_content_hash(
            {
                "title": item.get("title"),
                "company": item.get("company"),
                "description": str(item.get("description", ""))[:6000],
            }
        )
        item["contact_priority"] = (item["selected_contact"] or {}).get(
            "contact_priority", ""
        )
        item["research_cache"] = {
            "llm_status": research.get("llm_status"),
            "model_id": research.get("model_id", ""),
            "cache_key": (research.get("model_usage") or {}).get("cache_key", ""),
        }
    create_artifacts(output, output_root, max_artifacts=max_artifacts)
    for item in output:
        draft = draft_outreach(item)
        draft["validation_errors"] = validate_outreach(draft)
        if draft["validation_errors"]:
            draft["send_status"] = "blocked_validation"
        item["outreach"] = draft
        item["strategy_id"] = draft.get("strategy_id", "")
    return output


def _queue_age_days(first_seen: dict[str, str], run_date: date, item_id: str) -> int:
    try:
        seen = datetime.fromisoformat(str(first_seen.get(item_id, run_date.isoformat()))).date()
    except ValueError:
        return 0
    return max(0, (run_date - seen).days)


def send_streak_days(deliveries: dict[str, Record], run_date: date) -> int:
    """Consecutive days with emailed digest sends, ending today or yesterday."""
    active = {
        str(value.get("sent_at", ""))[:10]
        for value in deliveries.values()
        if isinstance(value, dict)
        and (value.get("opportunity_ids") or value.get("message_id"))
    }
    day, streak = run_date, 0
    if day.isoformat() not in active:
        day -= timedelta(days=1)
    while day.isoformat() in active:
        streak += 1
        day -= timedelta(days=1)
    return streak


GLANCE_FO_PHRASES = (
    "founder's office",
    "founder office",
    "founders office",
    "chief of staff",
    "founder associate",
    "ceo office",
    "generalist",
)
GLANCE_HIRING_TERMS = ("hiring", "opening", "apply", "looking for")
GLANCE_SENIORITY_EXCLUDE = (
    "0-3 years",
    "1+ year",
    "2+ year",
    "3+ year",
    "year experience",
    "years of experience",
    "experienced professional",
)


def select_glance_queue(scored: list[Record], max_items: int = 5) -> list[Record]:
    """LinkedIn posts worth Daksh's own 10-second glance, nothing more.

    These look FO-shaped and Bengaluru-mentioned but carry no structured
    employer, so the machine cannot qualify them. They stay ineligible,
    uncounted, and unemailed; the human opens the link and decides.
    """

    queue: list[Record] = []
    for item in scored:
        if item.get("source") != "linkedin_posts_apify" or item.get("eligible"):
            continue
        text = f"{item.get('title', '')} {item.get('description', '')}".casefold()
        if "intern" not in text and "fellow" not in text:
            continue
        if "bengaluru" not in text and "bangalore" not in text:
            continue
        if not any(term in text for term in GLANCE_HIRING_TERMS):
            continue
        if not any(phrase in text for phrase in GLANCE_FO_PHRASES):
            continue
        if any(pattern in text for pattern in GLANCE_SENIORITY_EXCLUDE):
            continue
        queue.append(
            {
                "id": item.get("id"),
                "excerpt": clean_text(item.get("description"))[:300],
                "source_url": item.get("source_url"),
                "apply_url": item.get("apply_url"),
            }
        )
        if len(queue) >= max(1, max_items):
            break
    return queue


def attach_send_loop(
    run: Record,
    *,
    run_date: date,
    first_seen: dict[str, str],
    sent_ids: set[str],
    deliveries: dict[str, Record],
    scoring: dict[str, Any],
) -> Record:
    """Push drafts out the door: quota queue, stale flags, and send streak.

    Reads delivery state only; every send stays manual and human-owned."""

    approved = list(run.get("digest_primary", [])) + list(run.get("digest_remote_fallback", []))
    unsent = sorted(
        (item for item in approved if str(item.get("id")) not in sent_ids),
        key=lambda item: (-int(item.get("score", 0) or 0), str(item.get("id"))),
    )
    quota = max(1, int(scoring.get("daily_send_quota", 3)))
    stale_after = int(scoring.get("stale_after_days", 3))
    entries = []
    for item in unsent:
        contact = item.get("selected_contact") or {}
        entries.append(
            {
                "id": item.get("id"),
                "company": item.get("company"),
                "title": item.get("title"),
                "score": item.get("score", 0),
                "age_days": _queue_age_days(first_seen, run_date, str(item.get("id"))),
                "resume": item.get("resume"),
                "apply_url": item.get("apply_url") or item.get("source_url"),
                "contact": contact.get("email") or contact.get("name", ""),
            }
        )
    queue = entries[:quota]
    queued_ids = {entry["id"] for entry in queue}
    stale = [
        entry for entry in entries
        if entry["age_days"] >= stale_after and entry["id"] not in queued_ids
    ]
    run["send_queue"] = queue
    run["stale_queue"] = stale
    run["send_streak_days"] = send_streak_days(deliveries, run_date)
    run["daily_send_quota"] = quota
    return run


def _validate_selected_links(records: list[Record]) -> None:
    for item in records:
        reasons = list(item.get("rejection_reasons") or [])
        if not item.get("eligible") and reasons != ["role_not_cross_functional"]:
            continue
        target = str(item.get("apply_url") or item.get("source_url") or "")
        result = validate_application_link(target)
        item["apply_link_validation"] = result
        if result.get("definitively_dead"):
            item["digest_approved"] = False
            item.setdefault("rejection_reasons", []).append("apply_link_dead")
        elif result.get("status") == "verification_required":
            item["apply_link_warning"] = "manual_verification_required"


def select_needs_verification(
    records: list[Record], scoring: dict[str, Any]
) -> list[Record]:
    """Leads dropped only because a LinkedIn link needs Daksh's own check.

    Policy allows retaining these as low-confidence unverified leads, so they
    are surfaced for manual review instead of being discarded. They stay
    rejected and ineligible: this reads the rejection list rather than
    changing it, so no scoring, digest or API path can promote one. The sole
    reason test matters - a record that is also stale, senior or out of scope
    is not worth a manual check.
    """
    tray = [
        item
        for item in records
        if list(item.get("rejection_reasons") or [])
        == ["linkedin_post_requires_manual_verification"]
    ]
    # score() returns 0 for every ineligible record, so it cannot rank these.
    # Freshest first is the ordering that helps a manual check.
    tray.sort(key=lambda item: str(item.get("posted_date") or ""), reverse=True)
    return tray[: int(scoring.get("max_needs_verification", 10))]


def _company_key(value: object) -> str:
    return "".join(character for character in clean_text(value).casefold() if character.isalnum())


def attach_company_provenance(
    records: list[Record], companies: list[Record]
) -> list[Record]:
    """Attach an official URL only when one reviewed company name is an exact match."""

    matches: dict[str, list[Record]] = {}
    for company in companies:
        key = _company_key(company.get("company"))
        if key and company.get("company_url"):
            matches.setdefault(key, []).append(company)
    output: list[Record] = []
    for record in records:
        item = dict(record)
        candidates = matches.get(_company_key(item.get("company")), [])
        if not item.get("company_url") and len(candidates) == 1:
            candidate = candidates[0]
            item["company_url"] = candidate["company_url"]
            item["company_url_basis"] = "reviewed_registry_exact_company_name"
            item["company_url_source"] = candidate.get("registry_url")
        output.append(item)
    return output


def _resolve_unresolved_via_firecrawl(
    events: list[Record], scoring: dict[str, Any]
) -> list[Record]:
    """Try Firecrawl-search resolution for funding events resolve_company_urls
    could not match by exact registry/opportunity name.

    A third pool on top of company_resolve.py's two exact-match pools, not a
    replacement -- resolve_company_url_via_search never accepts a domain
    without live on-page verification, so this stays inside the "no domain
    is ever guessed" rule. Gated on the same env vars as
    maybe_add_firecrawl_evidence; a run without Firecrawl configured leaves
    events exactly as resolve_company_urls returned them.
    """
    if os.getenv("PUBLIC_RESEARCH_PROVIDER", "source_evidence").casefold() != "firecrawl":
        return events
    if os.getenv("ENABLE_FIRECRAWL_RESEARCH", "").casefold() not in {"1", "true", "yes"}:
        return events
    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_key:
        return events
    cap = int(scoring.get("max_url_resolutions_per_run", 5))
    output: list[Record] = []
    attempted = 0
    for event in events:
        if event.get("company_url_basis") != "unresolved" or attempted >= cap:
            output.append(event)
            continue
        attempted += 1
        try:
            result = resolve_company_url_via_search(event.get("company", ""), api_key)
        except Exception as exc:
            item = dict(event)
            item["company_url_resolution_error"] = str(exc)[:300]
            output.append(item)
            continue
        if not result:
            output.append(event)
            continue
        item = dict(event)
        item.update(result)
        output.append(item)
    return output


def _dated_signal(signal: Record, run_date: date, max_age_days: int) -> bool:
    value = signal.get("date") or signal.get("event_date") or signal.get("posted_date")
    try:
        age = (run_date - datetime.fromisoformat(str(value)).date()).days
    except (TypeError, ValueError):
        return False
    return 0 <= age <= max_age_days and bool(signal.get("url") or signal.get("source_url"))


def _watchlist_to_companies(watchlist_config: dict[str, Any]) -> list[Record]:
    """Convert watchlist.yml company entries to Record format for deep research.

    Each watchlist company becomes a company record with site URL and lane.
    Building this list is free (no fetch, no LLM) -- the digest's watchlist
    movement section always uses it for display. Whether these records also
    enter the daily deep-research queue is gated separately, at the
    select_discovered_for_research call site, by watchlist.yml's
    deep_research flag.
    """
    output: list[Record] = []
    for company_cfg in watchlist_config.get("companies", []):
        if not isinstance(company_cfg, dict):
            continue
        name = clean_text(company_cfg.get("name", ""))
        site_url = clean_text(company_cfg.get("site_url", ""))
        if not name or not site_url:
            continue
        # Use a stable ID based on company name for the funding_event_id
        # so deep research results can be merged back
        company_id = stable_id("watchlist", name, prefix="watchlist")
        output.append(
            {
                "company": name,
                "company_url": site_url,
                "company_url_basis": "watchlist",
                "lane": clean_text(company_cfg.get("lane", "unknown")),
                "funding_event_id": company_id,
                "source": "watchlist",
            }
        )
    return output


def select_weekly_targets(
    companies: list[Record],
    funding_events: list[Record],
    run_date: date,
    scoring: dict[str, Any],
) -> list[Record]:
    """Return a separate Monday queue of evidence-backed founder targets."""

    if run_date.weekday() != 0:
        return []
    funding_by_company: dict[str, list[Record]] = {}
    for event in funding_events:
        funding_by_company.setdefault(_company_key(event.get("company")), []).append(
            {
                "type": "funding",
                "date": event.get("event_date"),
                "url": event.get("source_url"),
                "observation": event.get("headline"),
                "confidence": event.get("source_confidence"),
            }
        )
    candidates: list[Record] = []
    current_days = int(scoring.get("weekly_target_signal_days", 90))
    recent_days = int(scoring.get("weekly_target_recent_signal_days", 30))
    office_budget = int(scoring.get("weekly_office_check_max", 12))
    office_checks = 0
    for company in companies:
        location_text = clean_text(
            company.get("location") or company.get("bengaluru_presence")
        ).casefold()
        office_evidence: Record | None = None
        if "bengaluru" not in location_text and "bangalore" not in location_text:
            # HQ may be anywhere; a verified Bengaluru office also qualifies.
            # Bounded: at most office_budget live site checks per run.
            if office_checks >= office_budget or not clean_text(company.get("company_url")):
                continue
            office_checks += 1
            office_evidence = fetch_office_evidence(clean_text(company.get("company_url")))
            if office_evidence is None:
                continue
        count = company.get("employee_count")
        if isinstance(count, int) and count > int(scoring.get("max_employees", 400)):
            continue
        if company.get("lane") not in {"ai", "consumer"}:
            continue
        signals = [
            dict(item)
            for item in list(company.get("signals") or [])
            if isinstance(item, dict)
        ]
        signals.extend(funding_by_company.get(_company_key(company.get("company")), []))
        current = [item for item in signals if _dated_signal(item, run_date, current_days)]
        unique_signals: dict[str, Record] = {}
        for signal in current:
            key = clean_text(signal.get("url") or signal.get("source_url"))
            unique_signals.setdefault(key, signal)
        current = list(unique_signals.values())
        if len(current) < 2 or not any(
            _dated_signal(item, run_date, recent_days) for item in current
        ):
            continue
        item = dict(company)
        item.update(
            {
                "id": company.get("id") or stable_id(company.get("company"), prefix="target"),
                "title": "Founder’s Office / generalist internship",
                "weekly_target": True,
                "signals": current,
                "target_status": "manual_review_required",
            }
        )
        if office_evidence is not None:
            item["office_evidence"] = office_evidence
        candidates.append(item)
    candidates.sort(
        key=lambda item: max(clean_text(signal.get("date")) for signal in item["signals"]),
        reverse=True,
    )
    return candidates[: int(scoring.get("weekly_target_max_items", 3))]


def _empty_yield_bucket(source: str) -> Record:
    return {
        "source": source,
        "raw": 0,
        "unique": 0,
        "eligible": 0,
        "kimi_approved": 0,
        "manually_applied": 0,
        "replied": 0,
        "interviewed": 0,
        "rejection_reasons": {},
    }


def build_source_yield(
    raw_records: list[Record], unique_records: list[Record], published: list[Record]
) -> list[Record]:
    buckets: dict[str, Record] = {}
    for record in raw_records:
        source = clean_text(record.get("source") or "unknown")
        bucket = buckets.setdefault(source, _empty_yield_bucket(source))
        bucket["raw"] += 1
    for record in unique_records:
        source = clean_text(record.get("source") or "unknown")
        bucket = buckets.setdefault(source, _empty_yield_bucket(source))
        bucket["unique"] += 1
        bucket["eligible"] += int(bool(record.get("eligible")))
        status = clean_text(record.get("status")).casefold()
        reply = clean_text(record.get("reply_outcome")).casefold()
        interview = clean_text(record.get("interview_outcome")).casefold()
        bucket["manually_applied"] += int(status in {"applied", "sent_manually"})
        bucket["replied"] += int(bool(reply and reply != "no_reply"))
        bucket["interviewed"] += int(bool(interview and interview not in {"none", "no_interview"}))
        if not record.get("eligible"):
            reasons = bucket["rejection_reasons"]
            for reason in record.get("rejection_reasons", []) or []:
                reasons[reason] = reasons.get(reason, 0) + 1
    for record in published:
        source = clean_text(record.get("source") or "unknown")
        bucket = buckets.setdefault(source, _empty_yield_bucket(source))
        bucket["kimi_approved"] += int(bool(record.get("digest_approved")))
    results = []
    for bucket in buckets.values():
        reasons = bucket.pop("rejection_reasons")
        if reasons:
            top_reason, top_count = max(reasons.items(), key=lambda kv: kv[1])
            bucket["dominant_rejection_reason"] = top_reason
            bucket["dominant_rejection_count"] = top_count
        else:
            bucket["dominant_rejection_reason"] = ""
            bucket["dominant_rejection_count"] = 0
        results.append(bucket)
    return sorted(results, key=lambda item: item["source"])


def deterministic_candidate_count(
    raw_records: list[Record],
    run_date: date,
    config: dict[str, dict[str, Any]],
    first_seen_by_id: dict[str, str] | None = None,
) -> int:
    normalized = normalize_many(
        raw_records,
        config["roles"],
        config["scoring"],
        run_date.isoformat(),
        first_seen_by_id,
    )
    unique, _ = deduplicate(normalized)
    scored = score_many(unique, config["roles"], config["scoring"], run_date)
    selected = select_balanced(scored, config["scoring"])
    return len(selected["primary"]) + len(selected["remote_fallback"])


def _adaptive_apify_topup(
    raw: list[Record],
    health: list[Record],
    run_date: date,
    config: dict[str, dict[str, Any]],
    first_seen: dict[str, str],
    allow_paid_sources: bool = False,
) -> None:
    scoring = config["scoring"]
    minimum = int(scoring.get("daily_min_target", 5))
    # Daksh 2026-09-11: linkedin_every_run skips the below-minimum gate so the
    # actor fires on every scheduled run. The paid dual gate below still holds.
    if not scoring.get("linkedin_every_run", False):
        if deterministic_candidate_count(raw, run_date, config, first_seen) >= minimum:
            return
    if not scoring.get("adaptive_apify_topup", True):
        return
    if not allow_paid_sources:
        health.append(
            {
                "source_id": "linkedin_posts_apify",
                "status": "disabled",
                "record_count": 0,
                "checked_at": utc_timestamp(),
                "human_action": (
                    "Paid sources require --allow-paid-sources as well as "
                    "ENABLE_PERSONAL_APIFY_TOPUP=true."
                ),
            }
        )
        return
    if os.getenv("ENABLE_PERSONAL_APIFY_TOPUP", "false").casefold() not in {
        "1", "true", "yes"
    }:
        health.append(
            {
                "source_id": "linkedin_posts_apify",
                "status": "disabled",
                "record_count": 0,
                "checked_at": utc_timestamp(),
                "human_action": "Set ENABLE_PERSONAL_APIFY_TOPUP=true after the capped contract passes.",
            }
        )
        return
    source = next(
        (
            item
            for item in config["sources"].get("sources", [])
            if item.get("id") == "linkedin_posts_apify"
            and item.get("adaptive_enabled")
        ),
        None,
    )
    if not source:
        return
    try:
        from apify_sources import fetch_apify_actor

        records, metadata = fetch_apify_actor(
            source,
            config["sources"].get("apify", {}),
            int(config["sources"].get("timeout_seconds", 25)),
        )
        raw.extend(records)
        health.append(
            {
                "source_id": source["id"],
                "status": metadata.pop("health_status", "ok"),
                "record_count": len(records),
                "checked_at": utc_timestamp(),
                **metadata,
            }
        )
    except Exception as exc:
        text = str(exc)[:500]
        health.append(
            {
                "source_id": source["id"],
                "status": "budget_stopped" if "hard stop" in text else "failed",
                "record_count": 0,
                "error_type": type(exc).__name__,
                "error_message": text,
                "checked_at": utc_timestamp(),
                "human_action": "Inspect the capped actor contract and account-level monthly usage.",
            }
        )


# Statuses that mean Hunter never got a fair chance to find anything --
# misconfiguration or a hard error, not a real search that came up empty.
# These are what "complete_with_source_failures" should mean for Hunter;
# a monthly cap or a clean no-match is Hunter working as designed.
_HUNTER_FAILURE_STATUSES = {"no_api_key"}


def _hunter_source_health(hunter_ctx: dict[str, Any] | None) -> Record | None:
    """One aggregated source_health row summarizing every Hunter lookup this
    run. Every early return in hunter.py used to look identical (a silent
    None) from outside the module -- a missing HUNTER_API_KEY, a blocked
    domain, and a real HTTP error were indistinguishable, which is how the
    key going unwired to Modal could have gone unnoticed indefinitely."""
    if hunter_ctx is None:
        return None
    statuses: list[str] = hunter_ctx.get("statuses", [])
    if not statuses:
        return {
            "source_id": "hunter",
            "status": "ok",
            "record_count": 0,
            "human_action": "No records needed a Hunter lookup this run.",
        }
    from collections import Counter

    counts = Counter(statuses)
    found = counts.get("ok", 0) + counts.get("cache_hit", 0)
    is_failure = any(status in _HUNTER_FAILURE_STATUSES or status.startswith(("http_error", "error:")) for status in counts)
    summary = ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
    if "no_api_key" in counts:
        action = "HUNTER_API_KEY is not set for this run -- add it to the mounted secret."
    elif any(status.startswith(("http_error", "error:")) for status in counts):
        action = f"Hunter lookup errored ({summary}); inspect hunter.py's error handling."
    elif "quota_exhausted" in counts or "cap_reached" in counts:
        action = f"Hunter's free-tier budget was hit this run ({summary}); contacts fell back to research required."
    else:
        action = f"Hunter ran cleanly, {found} contact(s) found ({summary})."
    return {
        "source_id": "hunter",
        "status": "failed" if is_failure else "ok",
        "record_count": found,
        "human_action": action,
    }


def run_pipeline(
    raw_records: list[Record],
    source_health: list[Record],
    run_date: date,
    config: dict[str, dict[str, Any]],
    output_root: Path,
    funding_records: list[Record] | None = None,
    first_seen_by_id: dict[str, str] | None = None,
    run_kind: str = "fixture",
    validate_links: bool = False,
    role_judgements: dict[str, Any] | None = None,
    company_candidates: list[Record] | None = None,
    llm_cache: dict[str, Any] | None = None,
    hunter_state: Any | None = None,
) -> Record:
    llm_cache = llm_cache if llm_cache is not None else dict(role_judgements or {})
    # Built once, passed to every attach_contact call in this run -- funding
    # events and discovered/watchlist companies previously called bare
    # choose_contact with no Hunter fallback at all, which is why they were
    # the two buckets that never got a contact.
    hunter_ctx = (
        {"scoring": config["scoring"], "state": hunter_state, "month": run_date.strftime("%Y-%m")}
        if hunter_state is not None
        else None
    )
    raw_records = attach_company_provenance(raw_records, company_candidates or [])
    normalized = normalize_many(
        raw_records,
        config["roles"],
        config["scoring"],
        run_date.isoformat(),
        first_seen_by_id,
    )
    unique, duplicates = deduplicate(normalized)
    if validate_links:
        _validate_selected_links(unique)
    unique, role_judgement, role_judgement_cache = judge_cross_functional(
        unique, config["scoring"], llm_cache
    )
    scored = score_many(unique, config["roles"], config["scoring"], run_date)
    selected = select_balanced(scored, config["scoring"])
    primary, primary_llm = score_shortlist(
        selected["primary"], config["scoring"], "bengaluru_primary", cache=llm_cache
    )
    remote, remote_llm = score_shortlist(
        selected["remote_fallback"],
        config["scoring"],
        "india_remote_fallback",
        cache=llm_cache,
    )
    funding_primary, funding_extended, funding_excluded = select_funding_events(
        funding_records or [], run_date, config["scoring"]
    )
    resolved_funding = resolve_company_urls(
        funding_primary + funding_extended, company_candidates or [], scored
    )
    resolved_funding = _resolve_unresolved_via_firecrawl(resolved_funding, config["scoring"])
    resolved_by_id = {
        item["funding_event_id"]: item for item in resolved_funding
    }
    funding_primary = [resolved_by_id.get(item["funding_event_id"], item) for item in funding_primary]
    funding_extended = [resolved_by_id.get(item["funding_event_id"], item) for item in funding_extended]
    for event in funding_primary + funding_extended:
        # allow_llm only once a real company_url is resolved: with none, the
        # model has no evidence beyond the headline to ground a hypothesis
        # in, and the existing supported=false fail-closed gate would clear
        # the result anyway, so the call is skipped rather than spent.
        event["problem_research"] = research_funding_event(
            event, allow_llm=bool(event.get("company_url")), cache=llm_cache
        )
        # Funding events used to skip Hunter entirely (bare choose_contact,
        # no fallback), which is a real part of why contact was null on
        # every one of them -- see attach_contact's docstring.
        event["research"] = event["problem_research"]
        event["selected_contact"] = attach_contact(event, hunter_ctx)

    # Phase 2: Deep problem research for discovered companies
    # Load watchlist companies for digest display -- free, no fetch or LLM.
    watchlist_companies = _watchlist_to_companies(config.get("watchlist", {}))
    # Whether they also enter the daily deep-research queue (which bypasses
    # the evidence-minimum gate) is gated by deep_research in watchlist.yml.
    # Default false as of 2026-09-13: the same 3 fixed companies came back
    # insufficient_evidence every run, burning two Kimi calls each, twice
    # daily, for an answer that could not change. Deep-diving them is now a
    # one-shot manual step (pipeline.py --watchlist-prompts); their job
    # boards still get fetched every run via watchlist_board_sources, a
    # separate, cheap path this flag does not touch.
    watchlist_for_research = (
        watchlist_companies if config.get("watchlist", {}).get("deep_research", True) else []
    )
    # Select funded companies with resolved URLs for deep research,
    # plus watchlist companies admitted above (which bypass the evidence gate)
    discovered_for_research = select_discovered_for_research(
        funding_primary + funding_extended,
        config=config["scoring"],
        run_date=run_date,
        watchlist_companies=watchlist_for_research,
    )
    model_id = os.getenv("BEDROCK_RESEARCH_MODEL_ID", "")
    region = os.getenv("AWS_REGION", "")
    for company in discovered_for_research:
        if company.get("company_url"):
            company["deep_problem_research"] = research_deep_problem(
                company,
                llm_cache=llm_cache,
                config=config["scoring"],
                model_id=model_id,
                region=region,
            )

    # Phase 3: Generate prototype prompts for researched companies
    discovered_for_research = build_prompts_for_companies(
        discovered_for_research,
        llm_cache=llm_cache,
        model_id=model_id,
        region=region,
    )
    # build_prompts_for_companies returns copies, not the same objects
    # select_discovered_for_research handed it -- merge deep_problem_research
    # and prompt_generation back into funding_primary/funding_extended
    # explicitly by funding_event_id rather than relying on the earlier loop's
    # in-place mutation to have leaked through (it happened to, but a copy
    # anywhere in that chain would silently drop the result with no error).
    # Phase 5: draft problem-led outreach for each researched company. Funded
    # companies already got selected_contact from the funding-event loop
    # above; watchlist companies (never funding events) have not, so this is
    # the first point every discovered_for_research company definitely has
    # one. Without this, draft_problem_led_email's output never reaches a
    # real run -- the same "computed but never called" failure shape as the
    # earlier discovered_for_research/prompt_generation wiring gap.
    for company in discovered_for_research:
        contact = company.get("selected_contact") or {}
        if not contact:
            contact = attach_contact(company, hunter_ctx)
        elif not contact.get("email"):
            # research_deep_problem runs *after* the funding-event loop
            # attached this contact, and its five-page site fetch is the only
            # place a funded company's published_emails ever reach
            # _site_email. Skipping the retry here meant contacts.py's
            # research/deep_problem_research merge could never fire for the
            # bucket it was written for. choose_contact is free and offline,
            # so this costs nothing and spends no second Hunter lookup; the
            # earlier contact stays unless this actually turns up an address.
            rechosen = choose_contact(company)
            if rechosen.get("email"):
                contact = rechosen
        company["selected_contact"] = contact
        draft = draft_outreach(company)
        draft["validation_errors"] = validate_outreach(draft)
        if draft["validation_errors"]:
            draft["send_status"] = "blocked_validation"
        company["outreach"] = draft

    discovered_by_id = {
        item["funding_event_id"]: item for item in discovered_for_research
    }
    funding_primary = [
        discovered_by_id.get(item["funding_event_id"], item) for item in funding_primary
    ]
    funding_extended = [
        discovered_by_id.get(item["funding_event_id"], item) for item in funding_extended
    ]

    weekly_targets = select_weekly_targets(
        company_candidates or [], funding_primary + funding_extended, run_date, config["scoring"]
    )
    research_queue = (
        [item for item in primary if item.get("digest_approved")]
        + [item for item in remote if item.get("digest_approved")]
        + weekly_targets
    )
    enriched = enrich_selected(
        research_queue,
        output_root,
        int(config["scoring"]["max_artifacts"]),
        llm_cache,
        hunter_ctx=hunter_ctx,
    )
    enriched_by_id = {item["id"]: item for item in enriched}
    primary = [enriched_by_id.get(item["id"], item) for item in primary]
    remote = [enriched_by_id.get(item["id"], item) for item in remote]
    weekly_targets = [enriched_by_id.get(item["id"], item) for item in weekly_targets]
    usage_items = [
        item
        for item in (
            role_judgement.get("usage"),
            primary_llm.get("usage"),
            remote_llm.get("usage"),
            *[(item.get("research") or {}).get("model_usage") for item in primary + remote],
            *[(item.get("research") or {}).get("model_usage") for item in weekly_targets],
            *[item.get("usage") for item in source_health],
        )
        if isinstance(item, dict)
    ]
    llm_usage = usage_summary(usage_items)
    cache_statistics = {
        "entries": len(llm_cache),
        "hits": llm_usage["cache_hits"],
        "calls": llm_usage["calls"],
    }
    run_id = stable_id(
        run_kind,
        run_date.isoformat(),
        sorted(item["id"] for item in scored),
        sorted(
            item["funding_event_id"] for item in funding_primary + funding_extended
        ),
        prefix="run",
    )
    llm_statuses = {primary_llm.get("status"), remote_llm.get("status")}
    digest_usable = llm_statuses.issubset({"ok", "not_needed"})
    hunter_health = _hunter_source_health(hunter_ctx)
    if hunter_health is not None:
        source_health = [*source_health, hunter_health]
    return {
        "run_id": run_id,
        "run_kind": run_kind,
        "run_date": run_date.isoformat(),
        "internship_window_days": int(config["scoring"].get("max_posting_age_days", 10)),
        "funding_primary_window_days": int(
            config["scoring"].get("funding_primary_age_days", 15)
        ),
        "funding_extension_window_days": int(
            config["scoring"].get("funding_extension_age_days", 30)
        ),
        "daily_target": int(config["scoring"].get("daily_target", 10)),
        "daily_min_target": int(config["scoring"].get("daily_min_target", 5)),
        "status": "complete_with_source_failures"
        if any(item.get("status") == "failed" for item in source_health)
        else "complete",
        "raw_count": len(raw_records),
        "normalized_count": len(normalized),
        "deduplicated_count": len(unique),
        "duplicate_count": len(duplicates),
        "eligible_count": sum(bool(item.get("eligible")) for item in scored),
        "needs_verification": select_needs_verification(scored, config["scoring"]),
        "spotted_leads": [item for item in scored if item.get("source") == SPOTTED_SOURCE_ID],
        "glance_queue": select_glance_queue(scored, int(config["scoring"].get("glance_max_items", 5))),
        "weekly_targets": weekly_targets,
        "primary": primary,
        "remote_fallback": remote,
        "digest_primary": [item for item in primary if item.get("digest_approved")],
        "digest_remote_fallback": [
            item for item in remote if item.get("digest_approved")
        ],
        "llm_scoring": {
            "primary": primary_llm,
            "remote_fallback": remote_llm,
        },
        "role_judgement": role_judgement,
        "role_judgement_cache": role_judgement_cache,
        "llm_cache": llm_cache,
        "llm_usage": llm_usage,
        "cost_summary": {
            **llm_usage,
            "basis": "provider_token_usage; no verified dollar price configured",
        },
        "cache_statistics": cache_statistics,
        "digest_usable": digest_usable,
        "funding_primary": funding_primary,
        "funding_extended": funding_extended,
        "funding_excluded": funding_excluded,
        "discovered_for_research": discovered_for_research,
        "watchlist_companies": watchlist_companies,
        "all_scored": scored,
        "duplicates": duplicates,
        "source_health": source_health,
        "source_yield": build_source_yield(raw_records, scored, primary + remote),
        "completed_at": utc_timestamp(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the internship hunt pipeline")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixtures", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--input-json", type=Path)
    mode.add_argument("--digest-latest", action="store_true")
    mode.add_argument(
        "--watchlist-prompts",
        action="store_true",
        help=(
            "Write one deep-dive research prompt per watchlist.yml company and exit. "
            "No fetch, no LLM call -- paste the result into a fresh Claude Code session."
        ),
    )
    parser.add_argument("--run-date", type=date.fromisoformat)
    parser.add_argument("--publish-sheets", action="store_true")
    parser.add_argument("--send-digest", action="store_true")
    parser.add_argument("--no-state", action="store_true")
    parser.add_argument(
        "--allow-paid-sources",
        action="store_true",
        help="Permit explicitly enabled, budget-capped paid source calls.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and render without Sheets, Gmail, or opportunity state writes.",
    )
    return parser.parse_args()


def _atomic_write_json(path: Path, payload: Record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_latest_live(output_base: Path, json_path: Path, run: Record) -> None:
    pointer = {
        "run_id": run["run_id"],
        "run_kind": run["run_kind"],
        "path": str(json_path.resolve()),
        "completed_at": run.get("completed_at"),
    }
    _atomic_write_json(output_base / "latest-live.json", pointer)


def _load_latest_live(output_base: Path) -> tuple[Record, Path]:
    pointer_path = output_base / "latest-live.json"
    if not pointer_path.exists():
        raise RuntimeError("No saved latest-live pointer is available")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    path = Path(str(pointer.get("path", "")))
    if not path.is_file():
        raise RuntimeError("The latest-live run artifact is missing")
    run = json.loads(path.read_text(encoding="utf-8"))
    if run.get("run_kind") != "live" or run.get("run_id") != pointer.get("run_id"):
        raise RuntimeError("The latest-live pointer does not reference a valid live run")
    return run, path


def _self_digest_enabled() -> bool:
    return os.getenv("ENABLE_SELF_DIGEST", "false").casefold() in {"1", "true", "yes"}


_STALE_AFTER = timedelta(hours=18)


def _staleness_warning(run: Record) -> str:
    """Non-empty when the latest collect is old enough that 08:30 delivery
    would otherwise silently re-render a failed day as if it were fresh."""
    completed_at = run.get("completed_at")
    if not completed_at:
        return ""
    try:
        completed = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if datetime.now(completed.tzinfo) - completed > _STALE_AFTER:
        return (
            f"STALE DATA: the last successful collect finished at {completed_at}. "
            "A more recent scheduled collect appears to have failed; treat every "
            "match below as outdated until the pipeline is checked."
        )
    return ""


def _ist_delivery_key(run_id: str) -> str:
    return f"{datetime.now(IST).date().isoformat()}:{run_id}"


# Both addresses land in Daksh's inbox (alias setup); either may receive digests.
APPROVED_DIGEST_RECIPIENTS = frozenset(
    {"dakshinjain187@gmail.com", "dakshjainn02@gmail.com"}
)


def _send_once(run: Record, state: LocalState) -> tuple[str, str]:
    run_id = str(run["run_id"])
    delivery_key = _ist_delivery_key(run_id)
    # Keyed on the IST calendar date, not just run_id: a retry within the same
    # morning must not double-send, but a genuinely new day must always send
    # even if it happens to reference the same (stale) run artifact. The
    # legacy bare-run-id lookup covers deliveries recorded before this key
    # existed so they still count as already-sent.
    existing = state.digest_delivery_for_run(delivery_key, run_id)
    if existing.get("message_id"):
        return "digest_already_sent", str(existing["message_id"])
    if not run.get("digest_usable"):
        raise RuntimeError("Digest is unusable because Kimi shortlist scoring did not pass")
    if run.get("run_kind") != "live":
        raise RuntimeError("Self-digest delivery accepts live scheduled runs only")
    if os.getenv("BEDROCK_RESEARCH_MODEL_ID", "") != "moonshotai.kimi-k2.5":
        raise RuntimeError("Kimi K2.5 is not the pinned Bedrock research/scoring model")
    recipient = os.getenv("GMAIL_DIGEST_TO", "").strip().casefold()
    if recipient not in APPROVED_DIGEST_RECIPIENTS:
        raise RuntimeError("Self-digest recipient is not an approved Daksh address")
    sent_ids = state.sent_opportunity_ids()
    delivery_run = deepcopy(run)
    delivery_run["digest_primary"] = [
        item for item in run.get("digest_primary", []) if str(item.get("id")) not in sent_ids
    ]
    delivery_run["digest_remote_fallback"] = [
        item
        for item in run.get("digest_remote_fallback", [])
        if str(item.get("id")) not in sent_ids
    ]
    new_only = delivery_run["digest_primary"] + delivery_run["digest_remote_fallback"]
    opportunity_ids = [str(item["id"]) for item in new_only if item.get("id")]
    stale_notice = _staleness_warning(run)
    if stale_notice:
        delivery_run["staleness_warning"] = stale_notice
    # Daksh's explicit call (2026-09-12): a quiet day still gets mail. Silence
    # must mean the pipeline broke, never "nothing new to report" — those two
    # are indistinguishable from an empty inbox. The per-opportunity filter
    # above still decides what counts as *new*; it no longer decides whether
    # anything is sent. The verification tray and funding sections have their
    # own content independent of digest_primary/digest_remote_fallback and
    # were previously discarded along with the suppressed email.
    if opportunity_ids:
        subject = (
            f"{len(opportunity_ids)} new internship match"
            f"{'es' if len(opportunity_ids) != 1 else ''} - Rise"
        )
        status = "digest_sent"
    else:
        subject = "no new internship matches - Rise"
        status = "digest_sent_no_new_matches"
    if stale_notice:
        subject = f"[STALE] {subject}"
    body = render_digest(delivery_run)
    html_body = render_html_digest(delivery_run)
    message_id = send_self_digest(subject, body, html_body)
    state.record_digest_delivery(
        delivery_key,
        recipient,
        message_id,
        utc_timestamp(),
        opportunity_ids=opportunity_ids,
    )
    return status, message_id


def main() -> int:
    args = _parse_args()
    config = load_all()
    # The scheduler fires on IST wall-clock time inside a UTC container; using
    # date.today() here filed the 00:30 IST collect under the previous UTC day.
    run_date = args.run_date or datetime.now(IST).date()
    output_base = Path(
        os.getenv("PIPELINE_OUTPUT_DIR", str(AUTOMATION_ROOT / "out"))
    )
    state_base = Path(
        os.getenv("PIPELINE_STATE_DIR", str(AUTOMATION_ROOT / "state"))
    )
    state = LocalState(state_base / "state.json")
    llm_cache = {} if args.no_state else state.llm_cache()
    if args.watchlist_prompts:
        output_dir = output_base / run_date.isoformat() / "watchlist-prompts"
        written = write_watchlist_prompts(config["watchlist"], output_dir)
        print(
            json.dumps(
                {
                    "status": "watchlist_prompts_written",
                    "count": len(written),
                    "files": [str(path.resolve()) for path in written],
                },
                indent=2,
            )
        )
        return 0
    if args.digest_latest:
        # Unlike the --live path below, this branch used to have no exception
        # handling at all: any raise from _load_latest_live() or the guards
        # inside _send_once() crashed the scheduled Modal run with nothing in
        # the inbox and nothing distinguishing it from a normal quiet day.
        # Best-effort tell Daksh directly when that happens, then re-raise so
        # the run is still recorded as failed.
        try:
            run, run_path = _load_latest_live(output_base)
            digest_path = run_path.with_name(f"{run['run_id']}-digest.md")
            write_digest(digest_path, run)
            message_id = ""
            status = "digest_rendered"
            if args.send_digest and _self_digest_enabled():
                status, message_id = _send_once(run, state)
            print(
                json.dumps(
                    {
                        "run_id": run["run_id"],
                        "status": status,
                        "digest": str(digest_path.resolve()),
                        "digest_message_id": message_id,
                    },
                    indent=2,
                )
            )
            return 0
        except Exception as exc:
            if args.send_digest and _self_digest_enabled():
                try:
                    send_self_digest(
                        "[FAILED] internship digest delivery - Rise",
                        "The scheduled digest delivery failed before any mail could be "
                        f"rendered or sent.\n\n{type(exc).__name__}: {str(exc)[:500]}\n\n"
                        "Check the Modal app logs and out/latest-live.json.",
                    )
                except Exception:
                    pass  # noqa: BLE001 - failure-note delivery is best-effort only
            raise
    if args.live:
        live_sources = {
            **config["sources"],
            "sources": [
                *config["sources"].get("sources", []),
                *watchlist_board_sources(config.get("watchlist", {})),
            ],
        }
        raw, health = fetch_live(live_sources)
        preview_first_seen = (
            {} if args.no_state or args.dry_run else state.first_seen_dates()
        )
        _adaptive_apify_topup(
            raw,
            health,
            run_date,
            config,
            preview_first_seen,
            allow_paid_sources=args.allow_paid_sources,
        )
        spotted_path = AUTOMATION_ROOT / "input" / SPOTTED_FILE
        if spotted_path.is_file():
            spotted = load_spotted_leads(spotted_path)
            raw.extend(spotted)
            health.append(
                {
                    "source_id": SPOTTED_SOURCE_ID,
                    "status": "ok" if spotted else "zero_results",
                    "record_count": len(spotted),
                    "checked_at": utc_timestamp(),
                    "human_action": "Open each link yourself; the pipeline may not open LinkedIn.",
                }
            )
        raw, extraction = extract_linkedin_hiring_fields(
            raw, cache=llm_cache, scoring=config["scoring"]
        )
        if extraction.get("status") != "not_needed":
            candidates = int(extraction.get("candidates", extraction.get("sent", 0)) or 0)
            attempted = int(extraction.get("sent", 0) or 0)
            resolved = int(extraction.get("resolved", 0) or 0)
            health.append(
                {
                    "source_id": "linkedin_posts_apify_extraction",
                    "status": extraction.get("status"),
                    "record_count": resolved,
                    "checked_at": utc_timestamp(),
                    "usage": extraction.get("usage", {}),
                    "error_message": extraction.get("error", ""),
                    # candidates: posts that qualified for extraction; attempted:
                    # actually sent to the LLM. A gap between the two means the
                    # per-run cap is binding again and worth raising.
                    "candidates": candidates,
                    "attempted": attempted,
                    "resolved": resolved,
                    "unresolved": max(attempted - resolved, 0),
                    "skipped_over_cap": max(candidates - attempted, 0),
                    "human_action": (
                        "Inspect unresolved public posts; unproven fields remain rejected."
                        if extraction.get("status") != "ok"
                        else ""
                    ),
                }
            )
        funding_records, funding_health = fetch_funding_live(config["sources"])
        health.extend(funding_health)
        company_candidates, registry_health = fetch_registries(config["sources"])
        health.extend(registry_health)
        run_kind = "live_dry_run" if args.dry_run else "live"
    elif args.input_json:
        raw = load_json_records(args.input_json)
        funding_records = []
        company_candidates = []
        health = fixture_health(len(raw))
        health[0]["source_id"] = "human_import"
        run_kind = "human_import"
    else:
        fixture_path = AUTOMATION_ROOT / "fixtures" / "opportunities.json"
        raw = load_json_records(fixture_path, source_id="fixture")
        funding_records = []
        company_candidates = []
        health = fixture_health(len(raw))
        run_kind = "fixture"

    output_root = output_base / run_date.isoformat()
    first_seen = {} if args.no_state or args.dry_run else state.first_seen_dates()
    run = run_pipeline(
        raw,
        health,
        run_date,
        config,
        output_root,
        funding_records=funding_records,
        first_seen_by_id=first_seen,
        run_kind=run_kind,
        validate_links=run_kind.startswith("live"),
        role_judgements={} if args.no_state else state.role_judgements(),
        company_candidates=company_candidates,
        llm_cache=llm_cache,
        # Hunter spends free-tier credits, so dry and stateless runs skip it.
        hunter_state=None if args.no_state or args.dry_run else state,
    )
    run["company_candidates"] = company_candidates
    attach_send_loop(
        run,
        run_date=run_date,
        first_seen=first_seen,
        sent_ids=set() if args.no_state or args.dry_run else state.sent_opportunity_ids(),
        deliveries={} if args.no_state or args.dry_run else state.digest_deliveries(),
        scoring=config["scoring"],
    )
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / f"{run['run_id']}.json"
    digest_path = output_root / f"{run['run_id']}-digest.md"
    write_digest(digest_path, run)
    run["integrations"] = {}
    _atomic_write_json(json_path, run)
    if run_kind == "live":
        _write_latest_live(output_base, json_path, run)
    if not args.no_state and not args.dry_run:
        state.record_run(run)
    if args.publish_sheets and not args.dry_run:
        try:
            run["sheet_rows_written"] = publish_run(run)
            run["integrations"]["sheets"] = {"status": "ok"}
        except Exception as exc:
            run["integrations"]["sheets"] = {
                "status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            run["status"] = "complete_with_integration_failures"
    if args.send_digest and not args.dry_run:
        if _self_digest_enabled():
            try:
                status, message_id = _send_once(run, state)
                run["digest_message_id"] = message_id
                run["integrations"]["gmail"] = {"status": status}
            except Exception as exc:
                run["integrations"]["gmail"] = {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                }
                run["status"] = "complete_with_integration_failures"
        else:
            run["integrations"]["gmail"] = {"status": "skipped_disabled"}
    _atomic_write_json(json_path, run)

    print(
        json.dumps(
            {
                "run_id": run["run_id"],
                "status": run["status"],
                "raw": run["raw_count"],
                "eligible": run["eligible_count"],
                "primary": len(run["primary"]),
                "remote_fallback": len(run["remote_fallback"]),
                "output": str(json_path.resolve()),
                "digest": str(digest_path.resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
