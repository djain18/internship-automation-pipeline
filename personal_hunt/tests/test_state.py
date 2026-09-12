from pathlib import Path

from state import LocalState
from models import llm_cache_key, usage_summary


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


def test_digest_delivery_for_run_falls_back_to_legacy_bare_run_id_key(tmp_path: Path) -> None:
    state = LocalState(tmp_path / "state.json")
    # Pre-migration deliveries were keyed on the bare run_id (no IST date
    # prefix). The dated-key lookup must still recognize them as sent so a
    # legacy delivery is never re-sent under the new keying scheme.
    state.record_digest_delivery("run_legacy", "dakshinjain187@gmail.com", "msg_legacy", "now")
    assert state.digest_delivery_for_run("2026-09-12:run_legacy", "run_legacy")["message_id"] == "msg_legacy"
    assert state.digest_delivery_for_run("2026-09-13:run_new", "run_new") == {}


def test_llm_cache_persists_and_merges(tmp_path: Path) -> None:
    state = LocalState(tmp_path / "state.json")
    state.update_llm_cache({"key-a": {"payload": {"value": 1}}})
    state.update_llm_cache({"key-b": {"payload": {"value": 2}}})
    assert set(state.llm_cache()) == {"key-a", "key-b"}


def test_llm_cache_key_normalizes_content_and_invalidates_policy() -> None:
    first, _ = llm_cache_key("rank", "model-a", "v1", {"text": "a  b"})
    same, _ = llm_cache_key("rank", "model-a", "v1", {"text": "a b"})
    changed, _ = llm_cache_key("rank", "model-a", "v2", {"text": "a b"})
    assert first == same
    assert changed != first


def test_usage_summary_aggregates_calls_tokens_cache_and_cost() -> None:
    summary = usage_summary([
        {"calls": 1, "input_tokens": 10, "total_tokens": 13, "cost_usd": 0.01},
        {"cache_hits": 1, "output_tokens": 3, "elapsed_ms": 20},
    ])
    assert summary == {
        "calls": 1,
        "cache_hits": 1,
        "input_tokens": 10,
        "output_tokens": 3,
        "total_tokens": 13,
        "elapsed_ms": 20,
        "cost_usd": 0.01,
    }


def test_hunter_spend_and_domain_cache_are_month_scoped(tmp_path: Path) -> None:
    state = LocalState(tmp_path / "state.json")
    assert state.hunter_month_use("2026-09") == {"searches": 0, "verifications": 0}
    assert state.hunter_domain_cache("2026-09", "example.com") is None
    state.record_hunter_use("2026-09", "searches")
    state.cache_hunter_domain("2026-09", "Example.COM ", {"found": True, "email": "a@example.com"})
    assert state.hunter_month_use("2026-09") == {"searches": 1, "verifications": 0}
    assert state.hunter_domain_cache("2026-09", "example.com") == {"found": True, "email": "a@example.com"}
    assert state.hunter_domain_cache("2026-10", "example.com") is None
