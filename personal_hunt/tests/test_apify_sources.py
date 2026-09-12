import pytest
import json
from pathlib import Path

import apify_sources
from apify_sources import actor_health_status, fetch_apify_actor, map_actor_items

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_actor_health_status_uses_pipeline_vocabulary() -> None:
    assert actor_health_status("SUCCEEDED", 3) == "ok"
    assert actor_health_status("SUCCEEDED", 0) == "zero_results"
    assert actor_health_status("FAILED", 0) == "failed"
    assert actor_health_status("TIMED-OUT", 1) == "failed"


def test_monthly_budget_and_each_run_are_capped(monkeypatch) -> None:
    class FakeState:
        def apify_month_spend(self, _month: str) -> float:
            return 4.0

        def record_apify_run(self, *_args) -> None:
            return None

    class FakeResponse:
        def __init__(self, payload) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    post_params = {}

    def fake_post(_url, *, params, **_kwargs):
        post_params.update(params)
        return FakeResponse(
            {
                "data": {
                    "id": "actor_run_1",
                    "status": "SUCCEEDED",
                    "defaultDatasetId": "dataset_1",
                    "usageTotalUsd": 0.05,
                }
            }
        )

    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    monkeypatch.setattr(apify_sources, "_state", lambda: FakeState())
    monkeypatch.setattr(apify_sources, "account_monthly_usage", lambda *_args, **_kwargs: (4.0, 5.0))
    monkeypatch.setattr(apify_sources.requests, "post", fake_post)
    monkeypatch.setattr(
        apify_sources.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(
            [
                {
                    "id": "post_1",
                    "content": "Founder’s Office Intern in Bengaluru",
                    "linkedinUrl": "https://www.linkedin.com/posts/example",
                    "postedAt": {"date": "2026-09-09T00:00:00Z"},
                }
            ]
        ),
    )

    records, metadata = fetch_apify_actor(
        {
            "id": "linkedin_posts_apify",
            "adapter": "apify_linkedin_posts",
            "actor_id": "harvestapi/linkedin-post-search",
            "input": {"searchQueries": ["Founder office intern"]},
        },
        {"monthly_budget_usd": 5.0, "warn_at_usd": 5.0, "max_run_charge_usd": 0.25},
        25,
    )

    assert len(records) == 1
    assert post_params["maxTotalChargeUsd"] == 0.25
    assert metadata["health_status"] == "ok"
    assert metadata["actor_status"] == "succeeded"
    assert metadata["budget_warning"] is False
    assert metadata["monthly_hard_stop_usd"] == 5.0


def test_monthly_hard_stop_blocks_actor_before_spend(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    monkeypatch.setattr(apify_sources, "account_monthly_usage", lambda *_args, **_kwargs: (4.90, 5.0))
    monkeypatch.setattr(
        apify_sources.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("actor must not start after the hard stop"),
    )
    with pytest.raises(RuntimeError, match="All Apify keys are unusable"):
        fetch_apify_actor(
            {
                "id": "linkedin_posts_apify",
                "adapter": "apify_linkedin_posts",
                "actor_id": "harvestapi/linkedin-post-search",
                "input": {"searchQueries": ["Founder office intern"]},
            },
            {"monthly_budget_usd": 5.0, "max_run_charge_usd": 0.25},
            25,
        )


def _clear_key_env(monkeypatch) -> None:
    for name in ("APIFY_TOKEN", "APIFY_API_TOKEN", *(f"APIFY_TOKEN_{i}" for i in range(1, 11))):
        monkeypatch.delenv(name, raising=False)


class _RecordingState:
    def __init__(self, spend: float = 0.0) -> None:
        self.spend = spend
        self.recorded: list = []

    def apify_month_spend(self, _month: str) -> float:
        return self.spend

    def record_apify_run(self, *args) -> None:
        self.recorded.append(args)


class _OkResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def _run_payload(run_id="actor_run_1", usage=0.05):
    return {
        "data": {
            "id": run_id,
            "status": "SUCCEEDED",
            "defaultDatasetId": "dataset_1",
            "usageTotalUsd": usage,
        }
    }


def _source():
    return {
        "id": "linkedin_posts_apify",
        "adapter": "apify_linkedin_posts",
        "actor_id": "harvestapi/linkedin-post-search",
        "input": {"searchQueries": ["Founder office intern"]},
    }


def test_rotation_uses_second_key_after_401(monkeypatch) -> None:
    _clear_key_env(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN_1", "bad-key")
    monkeypatch.setenv("APIFY_TOKEN_2", "good-key")
    state = _RecordingState()
    seen_tokens = []

    def fake_limits(token, **_kwargs):
        if token == "bad-key":
            raise RuntimeError("401 Unauthorized")
        return (1.0, 5.0)

    def fake_post(_url, *, params, **_kwargs):
        seen_tokens.append(params["token"])
        return _OkResponse(_run_payload())

    monkeypatch.setattr(apify_sources, "_state", lambda: state)
    monkeypatch.setattr(apify_sources, "account_monthly_usage", fake_limits)
    monkeypatch.setattr(apify_sources.requests, "post", fake_post)
    monkeypatch.setattr(
        apify_sources.requests, "get",
        lambda *_a, **_k: _OkResponse([{"id": "p1", "content": "x"}]),
    )
    _records, metadata = fetch_apify_actor(_source(), {"monthly_budget_usd": 5.0, "max_run_charge_usd": 0.70}, 25)
    assert metadata["apify_slot"] == "key_2"
    assert seen_tokens == ["good-key"]
    assert state.recorded[0][-1] == "key_2"


def test_rotation_fails_closed_when_all_keys_bad(monkeypatch) -> None:
    _clear_key_env(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN_1", "bad-1")
    monkeypatch.setenv("APIFY_TOKEN_2", "bad-2")
    monkeypatch.setattr(apify_sources, "_state", lambda: _RecordingState())
    monkeypatch.setattr(
        apify_sources, "account_monthly_usage",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("403 Forbidden")),
    )
    monkeypatch.setattr(
        apify_sources.requests, "post",
        lambda *_a, **_k: pytest.fail("actor must not start without a usable key"),
    )
    with pytest.raises(RuntimeError, match="All Apify keys are unusable"):
        fetch_apify_actor(_source(), {"monthly_budget_usd": 5.0, "max_run_charge_usd": 0.70}, 25)


def test_exhausted_slot_is_skipped_for_next_key(monkeypatch) -> None:
    _clear_key_env(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN_1", "spent-key")
    monkeypatch.setenv("APIFY_TOKEN_2", "fresh-key")
    state = _RecordingState()

    def fake_limits(token, **_kwargs):
        return (4.90, 5.0) if token == "spent-key" else (0.0, 5.0)

    monkeypatch.setattr(apify_sources, "_state", lambda: state)
    monkeypatch.setattr(apify_sources, "account_monthly_usage", fake_limits)
    monkeypatch.setattr(
        apify_sources.requests, "post",
        lambda _u, *, params, **_k: _OkResponse(_run_payload()) if params["token"] == "fresh-key" else pytest.fail("exhausted key must not run"),
    )
    monkeypatch.setattr(
        apify_sources.requests, "get",
        lambda *_a, **_k: _OkResponse([{"id": "p1", "content": "x"}]),
    )
    _records, metadata = fetch_apify_actor(_source(), {"monthly_budget_usd": 5.0, "max_run_charge_usd": 0.70}, 25)
    assert metadata["apify_slot"] == "key_2"


def test_shared_monthly_stop_blocks_before_any_key(monkeypatch) -> None:
    _clear_key_env(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN_1", "any-key")
    monkeypatch.setattr(apify_sources, "_state", lambda: _RecordingState(spend=4.90))
    monkeypatch.setattr(
        apify_sources, "account_monthly_usage",
        lambda *_a, **_k: pytest.fail("no account check after the shared stop"),
    )
    with pytest.raises(RuntimeError, match="monthly hard stop"):
        fetch_apify_actor(_source(), {"monthly_budget_usd": 5.0, "max_run_charge_usd": 0.70}, 25)


def test_default_per_run_cap_is_070(monkeypatch) -> None:
    _clear_key_env(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN", "solo-key")
    post_params = {}
    monkeypatch.setattr(apify_sources, "_state", lambda: _RecordingState())
    monkeypatch.setattr(apify_sources, "account_monthly_usage", lambda *_a, **_k: (0.0, 0.0))
    monkeypatch.setattr(
        apify_sources.requests, "post",
        lambda _u, *, params, **_k: (post_params.update(params), _OkResponse(_run_payload()))[1],
    )
    monkeypatch.setattr(
        apify_sources.requests, "get",
        lambda *_a, **_k: _OkResponse([{"id": "p1", "content": "x"}]),
    )
    fetch_apify_actor(_source(), {}, 25)
    assert post_params["maxTotalChargeUsd"] == 0.70


def test_social_actor_records_are_forced_low_and_unverified() -> None:
    records = map_actor_items(
        [
            {
                "id": "post_1",
                "text": "Founder’s Office Intern in Bengaluru",
                "url": "https://x.com/example/status/1",
                "createdAt": "2026-09-09T00:00:00Z",
                "author": {"name": "Example Startup"},
            }
        ],
        {"id": "x_posts_apify", "adapter": "apify_x_posts"},
    )
    assert records[0]["source_confidence"] == "low"
    assert records[0]["verification_status"] == "machine_collected_unverified"
    assert records[0]["posted_at"] == "2026-09-09T00:00:00Z"


def test_linkedin_actor_nested_posted_date_is_mapped() -> None:
    records = map_actor_items(
        [
            {
                "id": "post_1",
                "content": "Founder’s Office Intern in Bengaluru",
                "linkedinUrl": "https://www.linkedin.com/posts/example",
                "postedAt": {"date": "2026-09-08T10:30:00Z"},
                "author": {"name": "Example Founder"},
            }
        ],
        {"id": "linkedin_posts_apify", "adapter": "apify_linkedin_posts"},
    )
    assert records[0]["posted_at"] == "2026-09-08T10:30:00Z"
    assert records[0]["description"] == "Founder’s Office Intern in Bengaluru"
    assert records[0]["company"] == ""
    assert records[0]["title"] == ""


def test_linkedin_mojibaked_apostrophe_is_repaired() -> None:
    # UTF-8 bytes for "'" (U+2019) decoded as cp1252 upstream produce this
    # exact three-character mangling. The extraction validator in llm_rank.py
    # requires an exact quote match against the post text, so leaving this
    # unrepaired silently loses otherwise-good posts.
    mojibaked = "Weâ€™re hiring at Auraaison a Founderâ€™s Office Intern"
    records = map_actor_items(
        [
            {
                "id": "post_moji",
                "content": mojibaked,
                "linkedinUrl": "https://www.linkedin.com/posts/auraaisonn",
            }
        ],
        {"id": "linkedin_posts_apify", "adapter": "apify_linkedin_posts"},
    )
    assert records[0]["description"] == "We’re hiring at Auraaison a Founder’s Office Intern"


def test_linkedin_genuinely_clean_text_is_left_unchanged() -> None:
    clean = "We are hiring a Founder's Office Intern in Bengaluru"
    records = map_actor_items(
        [{"id": "post_clean", "content": clean, "linkedinUrl": "https://www.linkedin.com/posts/clean"}],
        {"id": "linkedin_posts_apify", "adapter": "apify_linkedin_posts"},
    )
    assert records[0]["description"] == clean


def test_linkedin_fixture_uses_only_structured_job_evidence() -> None:
    payload = json.loads((FIXTURES / "linkedin-posts-response.json").read_text(encoding="utf-8"))
    records = map_actor_items(payload, {"id": "linkedin_posts_apify", "adapter": "apify_linkedin_posts"})
    assert records[0]["company"] == "Fixture Labs"
    assert records[0]["title"] == "Founder's Office Intern"
    assert records[0]["location"] == "Bengaluru"
    assert records[0]["apply_url"] == "https://fixture.example/jobs/1"
    assert records[0]["posted_at"] == "2026-09-10T09:00:00Z"
    assert records[1]["company"] == ""
    assert records[1]["title"] == ""
    assert records[1]["location"] == ""


def test_x_actor_current_output_contract_is_mapped() -> None:
    records = map_actor_items(
        [
            {
                "id_str": "1891042203344556600",
                "url": "https://x.com/example/status/1891042203344556600",
                "date": "2026-09-09T08:30:00+00:00",
                "rawContent": "Generalist internship across growth and operations.",
                "user": {"displayname": "Example Startup"},
            }
        ],
        {"id": "x_posts_apify", "adapter": "apify_x_posts"},
    )
    assert records[0]["id"] == "1891042203344556600"
    assert records[0]["company"] == "Example Startup"
    assert records[0]["posted_at"] == "2026-09-09T08:30:00+00:00"
