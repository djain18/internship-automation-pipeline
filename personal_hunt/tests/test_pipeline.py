from datetime import date
import json
from pathlib import Path

import pytest

from config import AUTOMATION_ROOT, load_all
from fetch_sources import fixture_health, load_json_records
import pipeline
from pipeline import _send_once
from pipeline import _atomic_write_json, _load_latest_live, _write_latest_live
from pipeline import (
    _adaptive_apify_topup,
    attach_company_provenance,
    build_source_yield,
    run_pipeline,
    select_needs_verification,
    select_weekly_targets,
)
from pipeline import route_resume
from state import LocalState


def test_fixture_pipeline_enforces_gates_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    # Deterministic gates must hold with Bedrock off, whatever the machine runs.
    monkeypatch.setenv("ENABLE_BEDROCK", "false")
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")
    health = fixture_health(len(records))
    first = run_pipeline(records, health, date(2026, 9, 8), config, tmp_path / "first")
    second = run_pipeline(records, health, date(2026, 9, 8), config, tmp_path / "second")

    assert first["run_id"] == second["run_id"]
    assert first["duplicate_count"] == 1
    assert {item["company"] for item in first["primary"]} == {
        "Nebula AI", "HomeGlow", "AgentNest", "CartCraft"
    }
    assert [item["company"] for item in first["remote_fallback"]] == ["RemoteFlow AI"]
    rejected = {
        item["company"]: item["rejection_reasons"]
        for item in first["all_scored"]
        if not item["eligible"]
    }
    assert "company_above_400_employees" in rejected["Mega AI Corporation"]
    assert "specialist_only_role" in rejected["CodeOnly"]
    assert "excluded_source" in rejected["Excluded Startup"]
    assert all("outreach" not in item for item in first["primary"])
    assert sum(bool(item.get("artifact_path")) for item in first["primary"]) == 0


def test_only_kimi_approved_records_are_researched(monkeypatch, tmp_path: Path) -> None:
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")
    researched: list[str] = []

    def fake_score(items, _scoring, section, cache=None):
        del cache
        output = []
        for index, item in enumerate(items):
            copy = dict(item)
            copy.update(
                {
                    "digest_approved": index == 0,
                    "llm_rank": index + 1,
                    "llm_fit_score": 90 if index == 0 else 50,
                    "llm_relevant": index == 0,
                    "llm_spam": False,
                    "llm_rank_reason": "fixture",
                    "llm_rank_status": "ok",
                }
            )
            output.append(copy)
        return output, {"status": "ok", "section": section}

    def fake_research(items, cache=None):
        del cache
        researched.extend(item["id"] for item in items)
        return [
            {
                "status": "provisional",
                "evidence": item.get("evidence", []),
                "observed_problem_signal": "The listing names an operational responsibility.",
                "inference": "The team may need help executing it.",
                "why_it_matters": "The work is part of the advertised role.",
                "solution_concept": "Prepare a small evidence-backed workflow review.",
                "uncertainty": "Confirm priorities with the company.",
            }
            for item in items
        ]

    monkeypatch.setattr(pipeline, "score_shortlist", fake_score)
    monkeypatch.setattr(pipeline, "research_records", fake_research)
    run = run_pipeline(records, [], date(2026, 9, 8), config, tmp_path / "run")

    approved = run["digest_primary"] + run["digest_remote_fallback"]
    assert set(researched) == {item["id"] for item in approved}
    assert all("research" not in item for item in run["primary"] if not item["digest_approved"])


def test_resume_routing_prioritizes_role_family() -> None:
    assert route_resume(
        {
            "title": "Founder’s Office Intern",
            "description": "AI operations and growth",
            "lane": "ai",
        }
    ) == "Daksh-Jain-founders_office"
    assert route_resume(
        {
            "title": "AI Automation Intern",
            "description": "Build LLM workflows",
            "lane": "ai",
        }
    ) == "Daksh-Jain-ai_automation"
    assert route_resume(
        {
            "title": "Growth Operations Intern",
            "description": "Consumer brand operations",
            "lane": "consumer",
        }
    ) == "Daksh-Jain-gtm"


def test_resume_routing_reads_the_title_not_the_description() -> None:
    """Real misroutes: the description's "high-growth" used to send a
    strategy role to the GTM resume, and a bare "ai" substring matched
    "retail"."""
    assert route_resume(
        {
            "title": "Strategy and Operations Intern",
            "description": "Join one of India's fastest high-growth AI labs.",
            "lane": "ai",
        }
    ) == "Daksh-Jain-founders_office"
    assert route_resume(
        {"title": "Retail Operations Intern", "description": "growth growth growth", "lane": ""}
    ) == "Daksh-Jain-ops"
    assert route_resume(
        {"title": "AI Growth Intern", "description": "", "lane": "ai"}
    ) == "Daksh-Jain-gtm"
    assert route_resume({"title": "Intern", "description": "growth", "lane": ""}) == "Daksh-Jain-Master"
    assert route_resume({"title": "Business Intern", "description": "", "lane": "consumer"}) == "Daksh-Jain-ops"


def test_self_digest_is_sent_once_per_live_run(monkeypatch, tmp_path: Path) -> None:
    state = LocalState(tmp_path / "state.json")
    sent_subjects: list[str] = []

    def fake_send(subject: str, _body: str, _html: str) -> str:
        sent_subjects.append(subject)
        return "gmail_message_1"

    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshinjain187@gmail.com")
    monkeypatch.setattr(pipeline, "send_self_digest", fake_send)
    run = {
        "run_id": "run_live_1",
        "run_date": "2026-09-09",
        "run_kind": "live",
        "digest_usable": True,
        "digest_primary": [{"id": "opp-1", "company": "Example", "title": "Founder’s Office Intern"}],
        "digest_remote_fallback": [],
        "primary": [],
        "remote_fallback": [],
        "funding_primary": [],
        "funding_extended": [],
        "source_health": [],
    }

    first = _send_once(run, state)
    second = _send_once(run, state)

    assert first == ("digest_sent", "gmail_message_1")
    assert second == ("digest_already_sent", "gmail_message_1")
    assert sent_subjects == ["1 new internship match - Rise"]


def test_self_digest_still_sends_when_every_match_was_already_sent(monkeypatch, tmp_path: Path) -> None:
    # 2026-09-12 incident: the day's only match was already emailed on a
    # previous day, the per-opportunity filter left nothing, and the whole
    # email was silently dropped. A quiet day must still produce mail.
    state = LocalState(tmp_path / "state.json")
    sent_subjects: list[str] = []

    def fake_send(subject: str, _body: str, _html: str = "") -> str:
        sent_subjects.append(subject)
        return "gmail_message_quiet"

    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshinjain187@gmail.com")
    monkeypatch.setattr(pipeline, "send_self_digest", fake_send)
    state.record_digest_delivery(
        "run_prior_day", "dakshinjain187@gmail.com", "gmail_prior", "2026-09-10T02:00:00Z",
        opportunity_ids=["opp-1"],
    )
    run = {
        "run_id": "run_quiet_day",
        "run_date": "2026-09-12",
        "run_kind": "live",
        "digest_usable": True,
        "digest_primary": [{"id": "opp-1", "company": "Example", "title": "Founder's Office Intern"}],
        "digest_remote_fallback": [],
        "primary": [],
        "remote_fallback": [],
        "funding_primary": [],
        "funding_extended": [],
        "source_health": [],
        "needs_verification": [{"id": "lead-1", "company": "Tray Co", "title": "Growth Intern"}],
    }

    status, message_id = _send_once(run, state)

    assert status == "digest_sent_no_new_matches"
    assert message_id == "gmail_message_quiet"
    assert sent_subjects == ["no new internship matches - Rise"]


def test_digest_key_is_per_ist_day_not_only_per_run_id(monkeypatch, tmp_path: Path) -> None:
    # A retry within the same IST day against the same run_id must not
    # double-send; a genuinely new IST day referencing the same run_id
    # (e.g. a failed later collect re-rendering the last good run) must send.
    state = LocalState(tmp_path / "state.json")
    calls: list[str] = []

    def fake_send(subject: str, _body: str, _html: str = "") -> str:
        calls.append(subject)
        return f"gmail_message_{len(calls)}"

    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshinjain187@gmail.com")
    monkeypatch.setattr(pipeline, "send_self_digest", fake_send)
    run = {
        "run_id": "run_same_artifact",
        "run_date": "2026-09-12",
        "run_kind": "live",
        "digest_usable": True,
        "digest_primary": [],
        "digest_remote_fallback": [],
        "primary": [],
        "remote_fallback": [],
        "funding_primary": [],
        "funding_extended": [],
        "source_health": [],
    }

    ist_days = iter(["2026-09-12", "2026-09-13", "2026-09-13"])
    monkeypatch.setattr(
        pipeline,
        "_ist_delivery_key",
        lambda run_id: f"{next(ist_days)}:{run_id}",
    )

    first = _send_once(run, state)
    second_new_day = _send_once(run, state)
    third_same_day_as_second = _send_once(run, state)

    assert first == ("digest_sent_no_new_matches", "gmail_message_1")
    # 2026-09-13 is a new IST day relative to the first send -> sends again.
    assert second_new_day == ("digest_sent_no_new_matches", "gmail_message_2")
    # A second call later the same IST day must not send a third time.
    assert third_same_day_as_second == ("digest_already_sent", "gmail_message_2")


def test_stale_collect_marks_digest_subject_and_body(monkeypatch, tmp_path: Path) -> None:
    state = LocalState(tmp_path / "state.json")
    captured: dict[str, str] = {}

    def fake_send(subject: str, body: str, _html: str = "") -> str:
        captured["subject"] = subject
        captured["body"] = body
        return "gmail_message_stale"

    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshinjain187@gmail.com")
    monkeypatch.setattr(pipeline, "send_self_digest", fake_send)
    run = {
        "run_id": "run_stale",
        "run_date": "2026-09-10",
        "run_kind": "live",
        "digest_usable": True,
        "digest_primary": [],
        "digest_remote_fallback": [],
        "primary": [],
        "remote_fallback": [],
        "funding_primary": [],
        "funding_extended": [],
        "source_health": [],
        "completed_at": "2026-09-10T00:00:00+00:00",
    }

    status, _ = _send_once(run, state)

    assert status == "digest_sent_no_new_matches"
    assert captured["subject"].startswith("[STALE]")
    assert "STALE DATA" in captured["body"]


def test_digest_latest_sends_failure_note_and_reraises_when_pointer_missing(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("PIPELINE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ENABLE_SELF_DIGEST", "true")
    monkeypatch.setattr(
        "sys.argv", ["pipeline.py", "--digest-latest", "--no-state", "--send-digest"]
    )
    failure_subjects: list[str] = []

    def fake_send(subject: str, _body: str, _html: str = "") -> str:
        failure_subjects.append(subject)
        return "gmail_message_failure"

    monkeypatch.setattr(pipeline, "send_self_digest", fake_send)

    with pytest.raises(RuntimeError, match="No saved latest-live pointer"):
        pipeline.main()

    assert failure_subjects == ["[FAILED] internship digest delivery - Rise"]


def test_self_digest_accepts_either_daksh_alias_and_rejects_other() -> None:
    assert "dakshinjain187@gmail.com" in pipeline.APPROVED_DIGEST_RECIPIENTS
    assert "dakshjainn02@gmail.com" in pipeline.APPROVED_DIGEST_RECIPIENTS
    assert "someone@example.com" not in pipeline.APPROVED_DIGEST_RECIPIENTS


def test_latest_digest_pointer_survives_newer_fixture_and_integration_failure(
    tmp_path: Path,
) -> None:
    live_path = tmp_path / "2026-09-09" / "run_live.json"
    live = {
        "run_id": "run_live",
        "run_kind": "live",
        "status": "complete",
        "completed_at": "2026-09-09T17:00:00+00:00",
    }
    _atomic_write_json(live_path, live)
    _write_latest_live(tmp_path, live_path, live)

    fixture_path = tmp_path / "2026-09-09" / "run_fixture.json"
    _atomic_write_json(
        fixture_path,
        {"run_id": "run_fixture", "run_kind": "fixture", "status": "complete"},
    )
    live["status"] = "complete_with_integration_failures"
    live["integrations"] = {"sheets": {"status": "failed"}}
    _atomic_write_json(live_path, live)

    loaded, loaded_path = _load_latest_live(tmp_path)
    assert loaded_path == live_path
    assert loaded["run_id"] == "run_live"
    assert loaded["status"] == "complete_with_integration_failures"
    assert json.loads((tmp_path / "latest-live.json").read_text(encoding="utf-8"))[
        "run_id"
    ] == "run_live"


def test_funding_event_research_only_allows_llm_when_company_url_resolved(
    monkeypatch, tmp_path: Path
) -> None:
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")
    calls: list[bool] = []

    def fake_research_funding_event(event, allow_llm=False, cache=None):
        calls.append(allow_llm)
        return {
            "status": "provisional",
            "problem_status": "insufficient_evidence",
            "problem_hypothesis": "",
        }

    monkeypatch.setattr(pipeline, "research_funding_event", fake_research_funding_event)
    funding_records = [
        {
            "funding_event_id": "funding_resolved",
            "company": "Resolvable Co",
            "event_date": "2026-09-08",
            "headline": "Resolvable Co raises $5 Mn",
            "source_url": "https://example.com/resolvable",
            "corroborating_urls": ["https://example.com/resolvable"],
        },
        {
            "funding_event_id": "funding_unresolved",
            "company": "Unresolvable Co",
            "event_date": "2026-09-08",
            "headline": "Unresolvable Co raises $5 Mn",
            "source_url": "https://example.com/unresolvable",
            "corroborating_urls": ["https://example.com/unresolvable"],
        },
    ]
    company_candidates = [
        {
            "company": "Resolvable Co",
            "company_url": "https://resolvable.example",
            "registry_url": "https://kalaari.com/portfolio",
        }
    ]
    run_pipeline(
        records,
        [],
        date(2026, 9, 8),
        config,
        tmp_path / "run",
        funding_records=funding_records,
        company_candidates=company_candidates,
    )
    assert sorted(calls) == [False, True]


def test_discovered_for_research_reaches_the_run_dict_with_prompts(
    monkeypatch, tmp_path: Path
) -> None:
    """Regression for a live-cloud-verification finding: Phase 2/3 results
    were computed but the final discovered_for_research list (carrying
    prompt_generation) was never written into run_pipeline's return dict,
    and deep_problem_research only survived by an unintended shared-object
    side effect that a copy anywhere in the chain would silently break."""
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")

    monkeypatch.setattr(
        pipeline, "research_funding_event",
        lambda event, allow_llm=False, cache=None: {
            "status": "provisional", "problem_status": "insufficient_evidence", "problem_hypothesis": "",
        },
    )
    monkeypatch.setattr(
        pipeline, "research_deep_problem",
        lambda company, **kwargs: {
            "problem_status": "inference_needs_validation",
            "observed_signals": [{"text": "real quote", "url": "https://resolvable.example/about"}],
            "evidence_count": 2,
        },
    )
    monkeypatch.setattr(
        pipeline, "build_prompts_for_companies",
        lambda companies, **kwargs: [
            {**company, "prompt_generation": {"prompt_text": "fake prompt", "llm_status": "ok"}}
            for company in companies
        ],
    )

    funding_records = [
        {
            "funding_event_id": "funding_resolved",
            "company": "Resolvable Co",
            "event_date": "2026-09-08",
            "headline": "Resolvable Co raises $5 Mn",
            "source_url": "https://example.com/resolvable",
            "corroborating_urls": ["https://example.com/resolvable"],
        },
    ]
    company_candidates = [
        {
            "company": "Resolvable Co",
            "company_url": "https://resolvable.example",
            "registry_url": "https://kalaari.com/portfolio",
        }
    ]
    result = run_pipeline(
        records,
        [],
        date(2026, 9, 8),
        config,
        tmp_path / "run",
        funding_records=funding_records,
        company_candidates=company_candidates,
    )

    assert "discovered_for_research" in result
    discovered = result["discovered_for_research"]
    # watchlist.yml's deep_research defaults to false as of 2026-09-13 (the
    # same 3 fixed companies burned two Kimi calls each, twice daily, for an
    # answer that never changed), so only the funded company enters the
    # daily deep-research queue. Watchlist companies are deep-dived by hand
    # instead (pipeline.py --watchlist-prompts).
    assert len(discovered) == 1
    company_names = {item["company"] for item in discovered}
    assert company_names == {"Resolvable Co"}
    # All should have prompt_generation
    assert all(item.get("prompt_generation", {}).get("prompt_text") == "fake prompt" for item in discovered)
    # Watchlist companies still reach the run dict, for the digest's
    # watchlist movement section -- just without deep research attached.
    watchlist_names = {item["company"] for item in result["watchlist_companies"]}
    assert watchlist_names == {"Emergent", "Lyzr AI", "AEOS"}
    # Every discovered company must have gone through outreach drafting --
    # draft_problem_led_email existed but was never called on this list
    # until this was fixed; watchlist companies in particular never went
    # through choose_contact anywhere else, so selected_contact must also
    # exist here rather than being missing.
    assert all("outreach" in item for item in discovered)
    assert all(item.get("selected_contact") for item in discovered)

    # And it must also have merged back into funding_primary, not only into
    # the standalone discovered_for_research list.
    resolved_event = next(
        item for item in result["funding_primary"] if item["funding_event_id"] == "funding_resolved"
    )
    assert resolved_event["prompt_generation"]["prompt_text"] == "fake prompt"
    assert resolved_event["deep_problem_research"]["problem_status"] == "inference_needs_validation"


def test_hunter_source_health_none_when_hunter_not_active() -> None:
    """No hunter_ctx (state disabled -- --no-state or --dry-run) means no
    Hunter row at all, not a misleading zero-activity row."""
    assert pipeline._hunter_source_health(None) is None


def test_hunter_source_health_reports_no_lookups_needed() -> None:
    row = pipeline._hunter_source_health({"scoring": {}, "state": None, "month": "2026-09"})
    assert row == {
        "source_id": "hunter",
        "status": "ok",
        "record_count": 0,
        "human_action": "No records needed a Hunter lookup this run.",
    }


def test_hunter_source_health_flags_missing_key_as_failed() -> None:
    """A missing HUNTER_API_KEY is the single highest-value line this
    plan adds -- it must render as a failure, not blend into ordinary
    'ran cleanly, found nothing' noise."""
    row = pipeline._hunter_source_health(
        {"scoring": {}, "state": None, "month": "2026-09", "statuses": ["no_api_key", "no_api_key"]}
    )
    assert row["status"] == "failed"
    assert "HUNTER_API_KEY" in row["human_action"]


def test_hunter_source_health_ok_on_a_clean_mix_of_finds_and_misses() -> None:
    row = pipeline._hunter_source_health(
        {"scoring": {}, "state": None, "month": "2026-09", "statuses": ["ok", "no_match", "cache_hit", "cap_reached"]}
    )
    assert row["status"] == "ok"
    assert row["record_count"] == 2  # ok + cache_hit


def test_hunter_source_health_flags_http_error_as_failed() -> None:
    row = pipeline._hunter_source_health(
        {"scoring": {}, "state": None, "month": "2026-09", "statuses": ["http_error:401"]}
    )
    assert row["status"] == "failed"


def test_watchlist_to_companies_always_returns_companies_for_digest_display() -> None:
    """Building the display list costs nothing (no fetch, no LLM) and must
    not depend on the deep_research flag -- the digest's watchlist movement
    section needs every company's name regardless of whether it also enters
    the daily research queue."""
    config = {"companies": [{"name": "Emergent", "site_url": "https://emergent.sh"}]}
    with_research = pipeline._watchlist_to_companies({**config, "deep_research": True})
    without_research = pipeline._watchlist_to_companies({**config, "deep_research": False})
    assert [item["company"] for item in with_research] == ["Emergent"]
    assert [item["company"] for item in without_research] == ["Emergent"]


def test_watchlist_deep_research_flag_gates_the_daily_queue_reversibly(
    monkeypatch, tmp_path: Path
) -> None:
    """deep_research: false (the 2026-09-13 default) keeps watchlist
    companies out of discovered_for_research; flipping it back to true from
    config alone, with no code change, restores the old behavior."""
    monkeypatch.setenv("ENABLE_BEDROCK", "false")
    config = load_all()
    config["watchlist"] = {
        "deep_research": False,
        "companies": [{"name": "Emergent", "site_url": "https://emergent.sh", "lane": "ai"}],
    }
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")
    health = fixture_health(len(records))

    off = run_pipeline(records, health, date(2026, 9, 8), config, tmp_path / "off")
    assert off["watchlist_companies"][0]["company"] == "Emergent"
    assert "Emergent" not in {item["company"] for item in off["discovered_for_research"]}

    config["watchlist"]["deep_research"] = True
    on = run_pipeline(records, health, date(2026, 9, 8), config, tmp_path / "on")
    assert "Emergent" in {item["company"] for item in on["discovered_for_research"]}


def test_discovered_company_gets_a_real_problem_led_draft(monkeypatch, tmp_path: Path) -> None:
    """With real-shaped evidence (a problem_hypothesis plus observed_signals),
    the discovered company's draft must actually be the problem-led email,
    not blocked_insufficient_evidence, and must reference the real signal
    text -- proving draft_problem_led_email's output, not just its presence,
    reaches the pipeline output."""
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")

    monkeypatch.setattr(
        pipeline, "research_funding_event",
        lambda event, allow_llm=False, cache=None: {
            "status": "provisional", "problem_status": "insufficient_evidence", "problem_hypothesis": "",
        },
    )
    monkeypatch.setattr(
        pipeline, "research_deep_problem",
        lambda company, **kwargs: {
            "problem_status": "inference_needs_validation",
            "problem_hypothesis": "Support onboarding strains after fresh funding.",
            "observed_signals": [
                {"text": "We are hiring five support engineers this quarter.", "url": "https://resolvable.example/careers"}
            ],
            "evidence_count": 2,
        },
    )
    monkeypatch.setattr(
        pipeline, "build_prompts_for_companies",
        lambda companies, **kwargs: [
            {**company, "prompt_generation": {"prompt_text": "fake prompt", "llm_status": "ok"}}
            for company in companies
        ],
    )

    funding_records = [
        {
            "funding_event_id": "funding_resolved",
            "company": "Resolvable Co",
            "event_date": "2026-09-08",
            "headline": "Resolvable Co raises $5 Mn",
            "source_url": "https://example.com/resolvable",
            "corroborating_urls": ["https://example.com/resolvable"],
        },
    ]
    company_candidates = [
        {
            "company": "Resolvable Co",
            "company_url": "https://resolvable.example",
            "registry_url": "https://kalaari.com/portfolio",
        }
    ]
    result = run_pipeline(
        records, [], date(2026, 9, 8), config, tmp_path / "run",
        funding_records=funding_records, company_candidates=company_candidates,
    )

    resolvable = next(
        item for item in result["discovered_for_research"] if item["company"] == "Resolvable Co"
    )
    draft = resolvable["outreach"]
    assert draft["draft_source"] == "problem_led"
    assert draft["send_status"] == "draft_needs_human_review"
    assert "support engineers" in draft["claude_prompt"]
    assert not draft["validation_errors"]


def _linkedin_lead(**overrides) -> dict:
    record = {
        "id": "lead-1",
        "company": "Signal Labs",
        "title": "Growth Intern",
        "score": 62,
        "eligible": False,
        "rejection_reasons": ["linkedin_post_requires_manual_verification"],
    }
    record.update(overrides)
    return record


def test_verification_tray_holds_only_sole_reason_leads() -> None:
    tray = select_needs_verification(
        [
            _linkedin_lead(),
            _linkedin_lead(id="lead-2", rejection_reasons=[
                "linkedin_post_requires_manual_verification", "posted_over_10_days"
            ]),
            _linkedin_lead(id="lead-3", rejection_reasons=["senior_role"]),
            _linkedin_lead(id="lead-4", rejection_reasons=[], eligible=True),
        ],
        {},
    )
    assert [item["id"] for item in tray] == ["lead-1"]


def test_verification_tray_rejects_a_linkedin_lead_with_any_second_reason() -> None:
    tray = select_needs_verification(
        [
            _linkedin_lead(id="sole-reason"),
            _linkedin_lead(
                id="also-stale",
                rejection_reasons=[
                    "linkedin_post_requires_manual_verification",
                    "posted_over_10_days",
                ],
            ),
        ],
        {},
    )

    assert [item["id"] for item in tray] == ["sole-reason"]


def test_verification_tray_is_capped_and_freshest_first() -> None:
    leads = [
        _linkedin_lead(id=f"lead-{index}", posted_date=f"2026-09-0{index}")
        for index in range(1, 7)
    ]
    tray = select_needs_verification(leads, {"max_needs_verification": 2})
    assert [item["posted_date"] for item in tray] == ["2026-09-06", "2026-09-05"]


def test_verification_tray_records_stay_rejected_and_uncounted(tmp_path: Path) -> None:
    config = load_all()
    records = load_json_records(
        AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture"
    )
    run = run_pipeline(records, [], date(2026, 9, 8), config, tmp_path / "run")
    approved_ids = {
        item["id"] for item in run["digest_primary"] + run["digest_remote_fallback"]
    }
    for item in run["needs_verification"]:
        assert item["eligible"] is False
        assert item["id"] not in approved_ids
    assert run["eligible_count"] == sum(
        bool(item.get("eligible")) for item in run["all_scored"]
    )


def test_verification_tray_record_can_never_be_counted_as_approved(
    tmp_path: Path,
) -> None:
    config = load_all()
    records = load_json_records(
        AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture"
    )
    run = run_pipeline(records, [], date(2026, 9, 8), config, tmp_path / "run")

    assert all(item.get("digest_approved") is False for item in run["needs_verification"])
    approved_count = len(run["digest_primary"]) + len(run["digest_remote_fallback"])
    assert approved_count == sum(
        bool(item.get("digest_approved"))
        for item in run["primary"] + run["remote_fallback"]
    )


def test_paid_topup_requires_explicit_cli_authorization(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_PERSONAL_APIFY_TOPUP", "true")
    monkeypatch.setattr(pipeline, "deterministic_candidate_count", lambda *_args: 0)
    health: list[dict] = []
    _adaptive_apify_topup([], health, date(2026, 9, 11), load_all(), {}, False)

    assert health[0]["status"] == "disabled"
    assert "--allow-paid-sources" in health[0]["human_action"]


def test_weekly_targets_are_monday_only_and_require_two_signals() -> None:
    scoring = load_all()["scoring"]
    companies = [
        {
            "id": "company-1",
            "company": "Signal AI",
            "company_url": "https://signal.example",
            "location": "Bengaluru",
            "lane": "ai",
            "employee_count": 50,
            "signals": [
                {"date": "2026-09-01", "url": "https://signal.example/launch", "observation": "Product launch"},
                {"date": "2026-08-01", "url": "https://signal.example/hiring", "observation": "Hiring expansion"},
            ],
        }
    ]

    assert select_weekly_targets(companies, [], date(2026, 9, 14), scoring)
    assert select_weekly_targets(companies, [], date(2026, 9, 15), scoring) == []
    one_signal = [{**companies[0], "signals": companies[0]["signals"][:1]}]
    assert select_weekly_targets(one_signal, [], date(2026, 9, 14), scoring) == []


def test_source_yield_keeps_raw_unique_and_approved_counts_separate() -> None:
    result = build_source_yield(
        [{"source": "yc"}, {"source": "yc"}, {"source": "ftb"}],
        [
            {
                "source": "yc",
                "eligible": True,
                "status": "applied",
                "reply_outcome": "positive",
                "interview_outcome": "scheduled",
            },
            {"source": "ftb", "eligible": False},
        ],
        [{"source": "yc", "digest_approved": True}],
    )
    by_source = {item["source"]: item for item in result}
    assert by_source["yc"] == {
        "source": "yc", "raw": 2, "unique": 1, "eligible": 1,
        "kimi_approved": 1, "manually_applied": 1, "replied": 1, "interviewed": 1,
        "dominant_rejection_reason": "", "dominant_rejection_count": 0,
    }


def test_source_yield_surfaces_dominant_rejection_reason_for_zero_yield_source() -> None:
    result = build_source_yield(
        [{"source": "linkedin"}] * 3,
        [
            {"source": "linkedin", "eligible": False, "rejection_reasons": ["missing_required_identity_or_source"]},
            {"source": "linkedin", "eligible": False, "rejection_reasons": ["missing_required_identity_or_source"]},
            {"source": "linkedin", "eligible": False, "rejection_reasons": ["location_out_of_scope"]},
        ],
        [],
    )
    by_source = {item["source"]: item for item in result}
    assert by_source["linkedin"]["eligible"] == 0
    assert by_source["linkedin"]["dominant_rejection_reason"] == "missing_required_identity_or_source"
    assert by_source["linkedin"]["dominant_rejection_count"] == 2


def test_company_url_requires_one_exact_reviewed_company_match() -> None:
    records = [{"company": "Signal AI", "company_url": ""}]
    companies = [
        {
            "company": "Signal AI",
            "company_url": "https://signal.example",
            "registry_url": "https://fund.example/portfolio",
        }
    ]
    attached = attach_company_provenance(records, companies)[0]
    assert attached["company_url"] == "https://signal.example"
    assert attached["company_url_source"] == "https://fund.example/portfolio"

    ambiguous = attach_company_provenance(records, companies * 2)[0]
    assert ambiguous.get("company_url", "") == ""


def _target_company(**overrides):
    company = {
        "id": "company-9",
        "company": "Faraway AI",
        "company_url": "https://faraway.example",
        "lane": "ai",
        "employee_count": 50,
        "signals": [
            {"date": "2026-09-01", "url": "https://faraway.example/launch", "observation": "Launch"},
            {"date": "2026-08-01", "url": "https://faraway.example/hiring", "observation": "Hiring"},
        ],
    }
    company.update(overrides)
    return company


def test_weekly_lane_accepts_verified_bengaluru_office_for_remote_hq(monkeypatch) -> None:
    import pipeline as pipeline_module

    evidence = {"observation": "Our Bengaluru office hosts...", "url": "https://faraway.example/about"}
    monkeypatch.setattr(pipeline_module, "fetch_office_evidence", lambda _url: evidence)
    scoring = load_all()["scoring"]
    targets = select_weekly_targets(
        [_target_company(location="Remote, worldwide")], [], date(2026, 9, 14), scoring
    )
    assert len(targets) == 1
    assert targets[0]["office_evidence"] == evidence


def test_weekly_lane_skips_unverifiable_office_and_respects_budget(monkeypatch) -> None:
    import pipeline as pipeline_module

    calls = []
    monkeypatch.setattr(
        pipeline_module, "fetch_office_evidence",
        lambda _url: (calls.append(1), None)[1],
    )
    scoring = dict(load_all()["scoring"])
    scoring["weekly_office_check_max"] = 1
    companies = [_target_company(id="c1"), _target_company(id="c2", company_url="")]
    targets = select_weekly_targets(companies, [], date(2026, 9, 14), scoring)
    assert targets == []
    assert len(calls) == 1


def _queue_run():
    def item(id, score):
        return {
            "id": id, "company": f"Co {id}", "title": "Founder's Office Intern",
            "score": score, "resume": "Daksh-Jain-Master",
            "apply_url": f"https://{id}.example/apply",
            "selected_contact": {"email": f"hire@{id}.example"},
        }

    return {
        "digest_primary": [item("a", 90), item("b", 80), item("c", 70), item("d", 60)],
        "digest_remote_fallback": [],
    }


def test_send_queue_respects_quota_and_skips_sent() -> None:
    from pipeline import attach_send_loop

    run = _queue_run()
    attach_send_loop(
        run, run_date=date(2026, 9, 11), first_seen={}, sent_ids={"a"},
        deliveries={}, scoring={"daily_send_quota": 2, "stale_after_days": 3},
    )
    assert [entry["id"] for entry in run["send_queue"]] == ["b", "c"]
    assert run["stale_queue"] == []
    assert run["send_streak_days"] == 0
    assert run["daily_send_quota"] == 2


def test_stale_queue_flags_aged_unsent_beyond_quota() -> None:
    from pipeline import attach_send_loop

    run = _queue_run()
    attach_send_loop(
        run, run_date=date(2026, 9, 11),
        first_seen={"a": "2026-09-11", "b": "2026-09-01", "c": "2026-09-11", "d": "2026-09-01"},
        sent_ids=set(), deliveries={},
        scoring={"daily_send_quota": 1, "stale_after_days": 3},
    )
    assert [entry["id"] for entry in run["send_queue"]] == ["a"]
    assert [entry["id"] for entry in run["stale_queue"]] == ["b", "d"]


def test_send_streak_counts_consecutive_days_only() -> None:
    from pipeline import send_streak_days

    assert send_streak_days({}, date(2026, 9, 11)) == 0
    deliveries = {
        "r1": {"sent_at": "2026-09-11T08:30:00+00:00", "opportunity_ids": ["a"]},
        "r2": {"sent_at": "2026-09-10T08:30:00+00:00", "opportunity_ids": ["b"]},
        "r3": {"sent_at": "2026-09-08T08:30:00+00:00", "opportunity_ids": ["c"]},
    }
    assert send_streak_days(deliveries, date(2026, 9, 11)) == 2
    assert send_streak_days(
        {"r2": deliveries["r2"]}, date(2026, 9, 11)
    ) == 1


def test_digest_renders_send_queue() -> None:
    from digest import render_digest
    from pipeline import attach_send_loop

    run = {
        "run_id": "run_q", "run_date": "2026-09-11", "status": "complete",
        "daily_target": 10, "daily_min_target": 5,
        **_queue_run(),
        "primary": [], "remote_fallback": [],
        "needs_verification": [], "weekly_targets": [],
        "funding_primary": [], "funding_extended": [],
        "source_health": [], "llm_usage": {},
        "cache_statistics": {}, "source_yield": [],
    }
    attach_send_loop(
        run, run_date=date(2026, 9, 11), first_seen={}, sent_ids=set(),
        deliveries={}, scoring={"daily_send_quota": 3, "stale_after_days": 3},
    )
    body = render_digest(run)
    assert "Today's send queue" in body
    assert "Co a" in body
    assert "Send streak: 0 days" in body


def test_spotted_leads_are_tracked_but_never_eligible(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "false")
    config = load_all()
    raw = [
        {
            "source": "human_spotted",
            "source_url": "https://www.linkedin.com/posts/example",
            "apply_url": "https://www.linkedin.com/posts/example",
            "company": "",
            "title": "",
            "description": "",
            "location": "",
            "posted_at": "",
            "source_confidence": "low",
            "verification_status": "human_spotted_unverified",
        }
    ]
    run = run_pipeline(raw, [], date(2026, 9, 11), config, tmp_path / "run")
    assert [item["source_url"] for item in run["spotted_leads"]] == [
        "https://www.linkedin.com/posts/example"
    ]
    assert run["eligible_count"] == 0
    assert run["digest_primary"] == [] and run["digest_remote_fallback"] == []


def test_every_run_mode_fires_topup_above_minimum(monkeypatch) -> None:
    import apify_sources

    monkeypatch.setenv("ENABLE_PERSONAL_APIFY_TOPUP", "true")
    monkeypatch.setattr(pipeline, "deterministic_candidate_count", lambda *_args: 99)
    calls = []
    monkeypatch.setattr(
        apify_sources,
        "fetch_apify_actor",
        lambda _source, _cfg, _timeout: (calls.append(1), ([{"id": "paid-1"}], {"health_status": "ok"}))[1],
    )
    config = load_all()
    config["scoring"]["linkedin_every_run"] = True
    raw: list = []
    health: list = []
    from pipeline import _adaptive_apify_topup as topup

    topup(raw, health, date(2026, 9, 11), config, {}, True)
    assert [item["id"] for item in raw] == ["paid-1"]
    assert health[0]["source_id"] == "linkedin_posts_apify"


def test_adaptive_mode_still_skips_topup_above_minimum(monkeypatch) -> None:
    import apify_sources

    monkeypatch.setenv("ENABLE_PERSONAL_APIFY_TOPUP", "true")
    monkeypatch.setattr(pipeline, "deterministic_candidate_count", lambda *_args: 99)
    monkeypatch.setattr(
        apify_sources,
        "fetch_apify_actor",
        lambda *_a, **_k: pytest.fail("adaptive mode must not fire above minimum"),
    )
    config = load_all()
    config["scoring"]["linkedin_every_run"] = False
    raw: list = []
    health: list = []
    from pipeline import _adaptive_apify_topup as topup

    topup(raw, health, date(2026, 9, 11), config, {}, True)
    assert raw == [] and health == []


def _glance_post(id, description, eligible=False, source="linkedin_posts_apify"):
    return {
        "id": id,
        "source": source,
        "eligible": eligible,
        "title": "",
        "description": description,
        "source_url": "https://linkedin.com/posts/" + id,
        "apply_url": "https://linkedin.com/posts/" + id,
    }


def test_glance_queue_keeps_only_fo_shaped_bengaluru_posts() -> None:
    from pipeline import select_glance_queue

    scored = [
        _glance_post("good", "Hiring Sales and Founder's Office Interns in Bengaluru, apply inside"),
        _glance_post("no-city", "Hiring Founder's Office Interns, remote worldwide, apply now"),
        _glance_post("no-fo", "Hiring Social Media Interns in Bengaluru, work from home"),
        _glance_post("senior", "Hiring Founder's Office Interns in Bengaluru with 0-3 years experience"),
        _glance_post("eligible", "Hiring Founder's Office Interns in Bengaluru", eligible=True),
        _glance_post("other-src", "Hiring Founder's Office Interns in Bengaluru", source="ftb_internships"),
    ]
    queue = select_glance_queue(scored, 5)
    assert [item["id"] for item in queue] == ["good"]
    assert queue[0]["excerpt"]
    assert queue[0]["source_url"].endswith("/good")


def test_glance_queue_is_capped() -> None:
    from pipeline import select_glance_queue

    scored = [
        _glance_post(f"p{i}", "Hiring Founder's Office Interns in Bengaluru, apply now")
        for i in range(8)
    ]
    assert len(select_glance_queue(scored, 5)) == 5


def test_digest_renders_glance_queue() -> None:
    from digest import render_digest

    run = {
        "run_id": "run_g",
        "run_date": "2026-09-11",
        "status": "complete",
        "daily_target": 10,
        "daily_min_target": 5,
        "digest_primary": [],
        "digest_remote_fallback": [],
        "primary": [],
        "remote_fallback": [],
        "needs_verification": [],
        "spotted_leads": [],
        "glance_queue": [
            {"id": "g1", "excerpt": "Hiring Founder's Office Interns", "source_url": "https://x.example/1"}
        ],
        "weekly_targets": [],
        "funding_primary": [],
        "funding_extended": [],
        "source_health": [],
        "llm_usage": {},
        "cache_statistics": {},
        "source_yield": [],
        "send_queue": [],
        "stale_queue": [],
        "send_streak_days": 0,
        "daily_send_quota": 3,
    }
    body = render_digest(run)
    assert "Worth a glance" in body
    assert "Hiring Founder's Office Interns" in body


def test_deep_research_published_emails_reach_the_selected_contact(
    monkeypatch, tmp_path: Path
) -> None:
    """The funding-event loop attaches selected_contact BEFORE
    research_deep_problem runs, so a funded company's deep-research
    published_emails could never reach contacts._site_email -- the guard in
    the discovered loop only re-chose a contact when there was none at all,
    and the funding loop always leaves a contact_research_required stub."""
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")

    monkeypatch.setattr(
        pipeline, "research_funding_event",
        lambda event, allow_llm=False, cache=None: {
            "status": "provisional", "problem_status": "insufficient_evidence",
            "problem_hypothesis": "", "published_emails": [],
        },
    )
    monkeypatch.setattr(
        pipeline, "research_deep_problem",
        lambda company, **kwargs: {
            "problem_status": "insufficient_evidence",
            "problem_hypothesis": "",
            "observed_signals": [],
            "evidence_count": 0,
            # The five-page deep fetch found what the funding-event fetch did not.
            "published_emails": ["founders@resolvable.example"],
        },
    )
    monkeypatch.setattr(
        pipeline, "build_prompts_for_companies",
        lambda companies, **kwargs: [
            {**company, "prompt_generation": {"prompt_text": "", "llm_status": "skipped"}}
            for company in companies
        ],
    )

    funding_records = [
        {
            "funding_event_id": "funding_resolved",
            "company": "Resolvable Co",
            "event_date": "2026-09-08",
            "headline": "Resolvable Co raises $5 Mn",
            "source_url": "https://example.com/resolvable",
            "corroborating_urls": ["https://example.com/resolvable"],
        },
    ]
    company_candidates = [
        {
            "company": "Resolvable Co",
            "company_url": "https://resolvable.example",
            "registry_url": "https://kalaari.com/portfolio",
        }
    ]
    result = run_pipeline(
        records, [], date(2026, 9, 8), config, tmp_path / "run",
        funding_records=funding_records, company_candidates=company_candidates,
    )

    resolvable = next(
        item for item in result["discovered_for_research"] if item["company"] == "Resolvable Co"
    )
    assert resolvable["selected_contact"]["email"] == "founders@resolvable.example"
    assert resolvable["selected_contact"]["basis"] == "site_published_role_mailbox"


def test_closed_listing_leaves_the_queue_and_the_next_entry_takes_its_slot() -> None:
    from pipeline import attach_send_loop

    run = _queue_run()
    seen: list[str] = []

    def closed_check(url: str) -> str:
        seen.append(url)
        return "this position has been filled" if url.startswith("https://b.") else ""

    attach_send_loop(
        run, run_date=date(2026, 9, 11), first_seen={}, sent_ids={"a"},
        deliveries={}, scoring={"daily_send_quota": 2, "stale_after_days": 3},
        closed_check=closed_check,
    )
    assert [entry["id"] for entry in run["send_queue"]] == ["c", "d"]
    assert [(entry["id"], entry["closed_signal"]) for entry in run["closed_queue"]] == [
        ("b", "this position has been filled")
    ]
    assert len(seen) == 3


def test_closed_listing_signal_never_opens_linkedin(monkeypatch) -> None:
    import company_site

    def fail(*_args, **_kwargs):
        raise AssertionError("LinkedIn must never be fetched")

    monkeypatch.setattr(company_site.requests.Session, "get", fail)
    assert company_site.closed_listing_signal("https://www.linkedin.com/jobs/view/1") == ""
    assert company_site.closed_listing_signal("https://lnkd.in/abc") == ""

