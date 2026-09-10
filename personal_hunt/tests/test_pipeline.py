from datetime import date
import json
from pathlib import Path

from config import AUTOMATION_ROOT, load_all
from fetch_sources import fixture_health, load_json_records
import pipeline
from pipeline import _send_once
from pipeline import _atomic_write_json, _load_latest_live, _write_latest_live
from pipeline import run_pipeline
from pipeline import route_resume
from state import LocalState


def test_fixture_pipeline_enforces_gates_and_is_idempotent(tmp_path: Path) -> None:
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
    assert all(item["outreach"]["send_status"] != "approved_manual_send" for item in first["primary"])
    assert sum(bool(item.get("artifact_path")) for item in first["primary"]) == 2


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
