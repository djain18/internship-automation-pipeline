import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import outreach_store
import private_api

from .test_outreach_store import lead, submitted

ROUTINE = {"Authorization": "Bearer routine-secret"}
DAKSH = {"Authorization": "Bearer firebase-ok"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    out = tmp_path / "out"
    run_path = out / "2026-09-14" / "run_a.json"
    run_path.parent.mkdir(parents=True)
    run = {
        "run_id": "run_a",
        "run_kind": "live",
        "run_date": "2026-09-14",
        "digest_primary": [lead("opp_1"), lead("opp_2")],
        "digest_remote_fallback": [],
    }
    run_path.write_text(json.dumps(run), encoding="utf-8")
    (out / "latest-live.json").write_text(json.dumps({"run_id": "run_a", "path": str(run_path)}), encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "state.json").write_text(json.dumps({"sent_opportunity_ids": ["opp_2"]}), encoding="utf-8")
    commits: list[int] = []
    monkeypatch.setattr(private_api, "OUTPUT_ROOT", out.resolve())
    monkeypatch.setattr(private_api, "STATE_PATH", state / "state.json")
    monkeypatch.setattr(private_api, "OUTREACH_PATH", state / "outreach.json")
    monkeypatch.setattr(private_api, "COMMIT", lambda: commits.append(1))
    monkeypatch.setenv("RISE_OUTREACH_TOKEN", "routine-secret")
    def verify(token):
        if token != "firebase-ok":
            raise private_api.HTTPException(status_code=401, detail="Invalid or expired sign-in")
        return {"email": "dakshjainn02@gmail.com", "email_verified": True}

    monkeypatch.setattr(private_api, "_verify_token", verify)
    monkeypatch.setattr(
        private_api, "_now", lambda: datetime(2026, 9, 14, 21, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    )
    client = TestClient(private_api.app)
    client.commits = commits
    client.state = state
    return client


def test_routine_endpoints_need_the_routine_token(api) -> None:
    assert api.get("/api/outreach/queue").status_code == 401
    assert api.get("/api/outreach/queue", headers={"Authorization": "Bearer wrong"}).status_code == 401
    # A Firebase session is not a routine credential.
    assert api.get("/api/outreach/queue", headers=DAKSH).status_code == 401


def test_routine_token_cannot_approve(api) -> None:
    api.post("/api/outreach/drafts", headers=ROUTINE, json={"run_id": "run_a", "drafts": [submitted()]})
    response = api.post("/api/outreach/drafts/opp_1/approve", headers=ROUTINE)
    assert response.status_code in {401, 403}


def test_full_flow_queue_draft_review_approve(api) -> None:
    queue = api.get("/api/outreach/queue", headers=ROUTINE).json()
    assert queue["run_id"] == "run_a"
    assert [item["lead_id"] for item in queue["leads"]] == ["opp_1"]  # opp_2 already sent

    wrong_run = api.post("/api/outreach/drafts", headers=ROUTINE, json={"run_id": "old", "drafts": [submitted()]})
    assert wrong_run.status_code == 409
    posted = api.post("/api/outreach/drafts", headers=ROUTINE, json={"run_id": "run_a", "drafts": [submitted()]})
    assert posted.json() == {"statuses": {"opp_1": "to_review"}}
    assert api.commits

    listing = api.get("/api/outreach/drafts", headers=DAKSH).json()
    assert listing["nextSlot"] == "2026-09-15T10:00:00+05:30"
    assert listing["drafts"][0]["status"] == "to_review"

    edited = api.patch("/api/outreach/drafts/opp_1", headers=DAKSH, json={"subject": "founders office note"})
    assert edited.json()["subject"] == "founders office note"
    assert api.patch("/api/outreach/drafts/opp_1", headers=DAKSH, json={"status": "sent"}).status_code == 400

    approved = api.post("/api/outreach/drafts/opp_1/approve", headers=DAKSH).json()
    assert approved["status"] == "approved"
    assert approved["slot"] == "2026-09-15T10:00:00+05:30"
    saved = outreach_store.load(api.state / "outreach.json")
    assert saved["drafts"]["opp_1"]["approval_hash"]

    assert api.post("/api/outreach/drafts/missing/reject", headers=DAKSH).status_code == 404


def test_cors_allows_the_review_page_to_write(api) -> None:
    response = api.options(
        "/api/outreach/drafts/opp_1/approve",
        headers={"Origin": "https://rise-web-kappa.vercel.app", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
