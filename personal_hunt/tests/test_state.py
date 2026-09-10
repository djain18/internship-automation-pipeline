from pathlib import Path

from state import LocalState


def test_first_seen_and_digest_delivery_are_stable(tmp_path: Path) -> None:
    state = LocalState(tmp_path / "state.json")
    state.record_run(
        {
            "run_id": "run_1",
            "run_date": "2026-09-01",
            "all_scored": [
                {"id": "opp_1", "company": "Co", "title": "Founder’s Office Intern"}
            ],
        }
    )
    state.record_run(
        {
            "run_id": "run_2",
            "run_date": "2026-09-09",
            "all_scored": [
                {"id": "opp_1", "company": "Co", "title": "Founder’s Office Intern"}
            ],
        }
    )
    assert state.first_seen_dates()["opp_1"] == "2026-09-01"
    state.record_digest_delivery("run_2", "daksh@example.com", "msg_1", "now")
    assert state.digest_delivery("run_2")["message_id"] == "msg_1"
    state.record_apify_run("2026-09", "actor/example", "actor_run_1", 0.25, 10, "SUCCEEDED", "now")
    state.record_apify_run("2026-09", "actor/example", "actor_run_1", 0.25, 10, "SUCCEEDED", "now")
    assert state.apify_month_spend("2026-09") == 0.25


def test_sent_opportunity_history_survives_new_runs(tmp_path: Path) -> None:
    state = LocalState(tmp_path / "state.json")
    state.record_digest_delivery(
        "run_1",
        "dakshinjain187@gmail.com",
        "message_1",
        "2026-09-10T02:30:00Z",
        opportunity_ids=["opp-1", "opp-2"],
    )
    state.record_digest_delivery(
        "run_2",
        "dakshinjain187@gmail.com",
        "message_2",
        "2026-09-11T02:30:00Z",
        opportunity_ids=["opp-2", "opp-3"],
    )
    assert state.sent_opportunity_ids() == {"opp-1", "opp-2", "opp-3"}
