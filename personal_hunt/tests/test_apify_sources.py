import pytest

import apify_sources
from apify_sources import actor_health_status, fetch_apify_actor, map_actor_items


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
    with pytest.raises(RuntimeError, match="monthly hard stop"):
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
