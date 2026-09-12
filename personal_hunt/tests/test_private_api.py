import json

from fastapi.testclient import TestClient

import private_api


def _write_live(tmp_path):
    run_path = tmp_path / "2026-09-10" / "run_live.json"
    run_path.parent.mkdir(parents=True)
    run = {
        "run_id": "run_live",
        "run_kind": "live",
        "run_date": "2026-09-10",
        "status": "complete",
        "completed_at": "2026-09-10T18:30:00+00:00",
        "digest_usable": True,
        "digest_primary": [{"id": "opp-1", "title": "Founder’s Office Intern", "artifact_path": "secret/path"}],
        "digest_remote_fallback": [],
        "primary": [],
        "remote_fallback": [],
        "funding_primary": [],
        "funding_extended": [],
        "source_health": [],
        "integrations": {},
        "weekly_targets": [{"id": "target-1", "research_cache_path": "private"}],
        "cost_summary": {"calls": 2, "credential": "private"},
        "source_yield": {"greenhouse": {"eligible": 1}},
        "cache_stats": {"hits": 4},
    }
    run_path.write_text(json.dumps(run), encoding="utf-8")
    (tmp_path / "latest-live.json").write_text(
        json.dumps({"run_id": "run_live", "path": str(run_path)}),
        encoding="utf-8",
    )


def test_private_api_requires_bearer_token():
    client = TestClient(private_api.app)
    assert client.get("/api/personal/latest").status_code == 401


def test_private_api_rejects_other_verified_email(monkeypatch):
    monkeypatch.setattr(
        private_api,
        "_verify_token",
        lambda _token: {"email": "someone@example.com", "email_verified": True},
    )
    client = TestClient(private_api.app)
    response = client.get(
        "/api/personal/latest", headers={"Authorization": "Bearer valid"}
    )
    assert response.status_code == 403


def test_private_api_accepts_second_approved_account(monkeypatch, tmp_path):
    _write_live(tmp_path)
    monkeypatch.setattr(private_api, "OUTPUT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(private_api, "STATE_PATH", tmp_path / "missing-state.json")
    monkeypatch.setattr(
        private_api,
        "_verify_token",
        lambda _token: {"email": "dakshjainn02@gmail.com", "email_verified": True},
    )
    client = TestClient(private_api.app)
    response = client.get(
        "/api/personal/latest", headers={"Authorization": "Bearer valid"}
    )
    assert response.status_code == 200


def test_private_api_rejects_unverified_approved_email(monkeypatch):
    monkeypatch.setattr(
        private_api,
        "_verify_token",
        lambda _token: {"email": "dakshjainn02@gmail.com", "email_verified": False},
    )
    client = TestClient(private_api.app)
    response = client.get(
        "/api/personal/latest", headers={"Authorization": "Bearer valid"}
    )
    assert response.status_code == 403


def test_private_api_returns_sanitized_live_run(monkeypatch, tmp_path):
    _write_live(tmp_path)
    monkeypatch.setattr(private_api, "OUTPUT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(private_api, "STATE_PATH", tmp_path / "missing-state.json")
    monkeypatch.setattr(
        private_api,
        "_verify_token",
        lambda _token: {
            "email": "dakshinjain187@gmail.com",
            "email_verified": True,
        },
    )
    client = TestClient(private_api.app)
    response = client.get(
        "/api/personal/latest",
        headers={"Authorization": "Bearer valid", "Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["bengaluru"][0]["id"] == "opp-1"
    assert "artifact_path" not in response.json()["bengaluru"][0]
    assert response.json()["weeklyTargets"] == [{"id": "target-1"}]
    assert response.json()["costSummary"] == {"calls": 2}
    assert response.json()["sourceYield"]["greenhouse"]["eligible"] == 1
    assert response.json()["cacheStatistics"] == {"hits": 4}
    assert response.json()["sendQueue"] == []
    assert response.json()["sendStreakDays"] == 0
