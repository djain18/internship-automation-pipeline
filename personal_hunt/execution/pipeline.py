from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

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
    os.environ.setdefault("AWS_REGION", "ap-south-1")
    os.environ.setdefault("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")

from artifacts import create_artifacts
from config import AUTOMATION_ROOT, load_all
from contacts import choose_contact
from dedupe import deduplicate
from digest import render_digest, render_html_digest, send_self_digest, write_digest
from discover_companies import fetch_registries
from fetch_sources import fetch_live, fixture_health, load_json_records
from funding import fetch_funding_live, select_funding_events
from llm_rank import judge_cross_functional, score_shortlist
from models import Record, stable_id, utc_timestamp
from normalize import normalize_many
from outreach import draft_outreach, validate_outreach
from research import research_funding_event, research_record
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
    records: list[Record], output_root: Path, max_artifacts: int
) -> list[Record]:
    output = deepcopy(records)
    for item in output:
        item["research"] = research_record(item)
        item["selected_contact"] = choose_contact(item)
        item["resume"] = route_resume(item)
    create_artifacts(output, output_root, max_artifacts=max_artifacts)
    for item in output:
        draft = draft_outreach(item)
        draft["validation_errors"] = validate_outreach(draft)
        if draft["validation_errors"]:
            draft["send_status"] = "blocked_validation"
        item["outreach"] = draft
    return output


def _validate_selected_links(records: list[Record]) -> None:
    for item in records:
        if not item.get("digest_approved"):
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
) -> None:
    scoring = config["scoring"]
    minimum = int(scoring.get("daily_min_target", 5))
    if deterministic_candidate_count(raw, run_date, config, first_seen) >= minimum:
        return
    if not scoring.get("adaptive_apify_topup", True):
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
) -> Record:
    normalized = normalize_many(
        raw_records,
        config["roles"],
        config["scoring"],
        run_date.isoformat(),
        first_seen_by_id,
    )
    unique, duplicates = deduplicate(normalized)
    unique, role_judgement, role_judgement_cache = judge_cross_functional(
        unique, config["scoring"], role_judgements
    )
    scored = score_many(unique, config["roles"], config["scoring"], run_date)
    selected = select_balanced(scored, config["scoring"])
    enriched_primary = enrich_selected(
        selected["primary"], output_root, int(config["scoring"]["max_artifacts"])
    )
    enriched_remote = enrich_selected(selected["remote_fallback"], output_root, 0)
    primary, primary_llm = score_shortlist(
        enriched_primary, config["scoring"], "bengaluru_primary"
    )
    remote, remote_llm = score_shortlist(
        enriched_remote, config["scoring"], "india_remote_fallback"
    )
    if validate_links and config["scoring"].get("validate_application_links", True):
        _validate_selected_links(primary)
        _validate_selected_links(remote)
    funding_primary, funding_extended, funding_excluded = select_funding_events(
        funding_records or [], run_date, config["scoring"]
    )
    for event in funding_primary + funding_extended:
        event["problem_research"] = research_funding_event(event)
        # Funding events skipped choose_contact entirely, which is why contact
        # was null on every one of them.
        event["research"] = event["problem_research"]
        event["selected_contact"] = choose_contact(event)
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
    return {
        "run_id": run_id,
        "run_kind": run_kind,
        "run_date": run_date.isoformat(),
        "internship_window_days": int(config["scoring"].get("max_posting_age_days", 7)),
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
        "digest_usable": digest_usable,
        "funding_primary": funding_primary,
        "funding_extended": funding_extended,
        "funding_excluded": funding_excluded,
        "all_scored": scored,
        "duplicates": duplicates,
        "source_health": source_health,
        "completed_at": utc_timestamp(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the internship hunt pipeline")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixtures", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--input-json", type=Path)
    mode.add_argument("--digest-latest", action="store_true")
    parser.add_argument("--run-date", type=date.fromisoformat)
    parser.add_argument("--publish-sheets", action="store_true")
    parser.add_argument("--send-digest", action="store_true")
    parser.add_argument("--no-state", action="store_true")
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


def _send_once(run: Record, state: LocalState) -> tuple[str, str]:
    existing = state.digest_delivery(str(run["run_id"]))
    if existing.get("message_id"):
        return "digest_already_sent", str(existing["message_id"])
    if not run.get("digest_usable"):
        raise RuntimeError("Digest is unusable because Kimi shortlist scoring did not pass")
    if run.get("run_kind") != "live":
        raise RuntimeError("Self-digest delivery accepts live scheduled runs only")
    if os.getenv("BEDROCK_RESEARCH_MODEL_ID", "") != "moonshotai.kimi-k2.5":
        raise RuntimeError("Kimi K2.5 is not the pinned Bedrock research/scoring model")
    recipient = os.getenv("GMAIL_DIGEST_TO", "").strip().casefold()
    if recipient != "dakshinjain187@gmail.com":
        raise RuntimeError("Self-digest recipient is not the approved Daksh address")
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
    opportunity_ids = [
        str(item["id"])
        for item in delivery_run["digest_primary"]
        + delivery_run["digest_remote_fallback"]
        if item.get("id")
    ]
    if not opportunity_ids:
        return "digest_skipped_no_new_matches", ""
    body = render_digest(delivery_run)
    html_body = render_html_digest(delivery_run)
    message_id = send_self_digest(
        f"{len(opportunity_ids)} new internship match{'es' if len(opportunity_ids) != 1 else ''} - Rise",
        body,
        html_body,
    )
    state.record_digest_delivery(
        str(run["run_id"]),
        recipient,
        message_id,
        utc_timestamp(),
        opportunity_ids=opportunity_ids,
    )
    return "digest_sent", message_id


def main() -> int:
    args = _parse_args()
    config = load_all()
    run_date = args.run_date or date.today()
    output_base = Path(
        os.getenv("PIPELINE_OUTPUT_DIR", str(AUTOMATION_ROOT / "out"))
    )
    state_base = Path(
        os.getenv("PIPELINE_STATE_DIR", str(AUTOMATION_ROOT / "state"))
    )
    state = LocalState(state_base / "state.json")
    if args.digest_latest:
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
    if args.live:
        raw, health = fetch_live(config["sources"])
        preview_first_seen = (
            {} if args.no_state or args.dry_run else state.first_seen_dates()
        )
        _adaptive_apify_topup(raw, health, run_date, config, preview_first_seen)
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
    )
    run["company_candidates"] = company_candidates
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
