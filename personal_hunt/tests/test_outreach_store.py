from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import outreach_store as store
from .test_check_draft import BODY

IST = ZoneInfo("Asia/Kolkata")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=IST)


def lead(lead_id="opp_1", **extra):
    return {
        "id": lead_id,
        "company": "Auraaison",
        "title": "Founder's Office Intern",
        "source_url": "https://www.linkedin.com/posts/auraaisonn_x",
        "apply_url": "admin@auraaison.com",
        "llm_fit_score": 92,
        "resume": "Daksh-Jain-founders_office",
        "description": "Hiring. Subject: Founder's Office",
        "selected_contact": {"email": "admin@auraaison.com", "source_url": "https://www.linkedin.com/posts/auraaisonn_x"},
        "outreach": {"claude_prompt": "# Auraaison: draft the outreach email"},
        **extra,
    }


def run(*leads):
    return {"run_id": "run_a", "run_date": "2026-09-14", "digest_primary": list(leads), "digest_remote_fallback": []}


def submitted(lead_id="opp_1", **overrides):
    return {
        "lead_id": lead_id,
        "to": "admin@auraaison.com",
        "to_source": "https://www.linkedin.com/posts/auraaisonn_x",
        "subject": "founder office intern",
        "body": BODY,
        "attachment": "Daksh-Jain-founders_office.pdf",
        "listing_subject": None,
        "follow_up": "A second idea on decision logs.",
        "linkedin_note": "Short note.",
        **overrides,
    }


@pytest.mark.parametrize(
    ("approved_at", "slot"),
    [
        ("2026-09-14T21:00", "2026-09-15T10:00"),  # Monday night -> Tuesday
        ("2026-09-15T08:59", "2026-09-15T10:00"),  # before the lock -> same day
        ("2026-09-15T09:00", "2026-09-16T10:00"),  # at the lock -> next weekday
        ("2026-09-18T21:00", "2026-09-21T10:00"),  # Friday night -> Monday
        ("2026-09-19T11:00", "2026-09-21T10:00"),  # Saturday -> Monday
        ("2026-09-21T07:00", "2026-09-21T10:00"),  # Monday morning -> Monday
    ],
)
def test_next_send_slot(approved_at, slot) -> None:
    assert store.next_send_slot(at(approved_at)) == at(slot)


def test_queue_skips_sent_and_already_drafted_leads() -> None:
    data = store.empty()
    queue = store.drafting_queue(run(lead("opp_1"), lead("opp_2"), lead("opp_3")), data, sent_ids={"opp_3"})
    assert [item["lead_id"] for item in queue] == ["opp_1", "opp_2"]
    first = queue[0]
    assert first["attachment"] == "Daksh-Jain-founders_office.pdf"
    assert first["contact"] == {"email": "admin@auraaison.com", "source": "https://www.linkedin.com/posts/auraaisonn_x"}
    assert first["prompt"].startswith("# Auraaison")
    # Rebuilt from current rules, not the stale prompt stored on the run.
    assert "What makes this obviously AI-written?" in first["prompt"]
    store.submit_drafts(data, "run_a", [submitted("opp_1")], at("2026-09-14T20:00"))
    assert [item["lead_id"] for item in store.drafting_queue(run(lead("opp_1"), lead("opp_2")), data, set())] == ["opp_2"]


def test_submit_sets_status_from_checks_and_address() -> None:
    data = store.empty()
    result = store.submit_drafts(
        data,
        "run_a",
        [submitted("ok"), submitted("noaddr", to=None, to_source=""), submitted("bad", subject="Hi")],
        at("2026-09-14T20:00"),
    )
    assert result == {"ok": "to_review", "noaddr": "needs_address", "bad": "blocked_validation"}
    assert data["drafts"]["bad"]["errors"]


def test_approval_requires_clean_draft_with_recipient() -> None:
    data = store.empty()
    store.submit_drafts(data, "run_a", [submitted("noaddr", to=None, to_source="")], at("2026-09-14T20:00"))
    with pytest.raises(store.DraftError):
        store.approve(data, "noaddr", at("2026-09-14T21:00"))
    store.edit_draft(data, "noaddr", {"to": "founder@auraaison.com"}, at("2026-09-14T21:05"))
    draft = data["drafts"]["noaddr"]
    assert draft["to_source"] == "entered_by_daksh"
    assert draft["status"] == "to_review"
    store.approve(data, "noaddr", at("2026-09-14T21:06"))
    assert data["drafts"]["noaddr"]["slot"] == "2026-09-15T10:00:00+05:30"


def test_edit_after_approval_clears_it_and_resubmit_never_touches_approved() -> None:
    data = store.empty()
    store.submit_drafts(data, "run_a", [submitted()], at("2026-09-14T20:00"))
    store.approve(data, "opp_1", at("2026-09-14T21:00"))
    store.submit_drafts(data, "run_a", [submitted(subject="other subject here")], at("2026-09-14T22:00"))
    assert data["drafts"]["opp_1"]["subject"] == "founder office intern"
    store.edit_draft(data, "opp_1", {"subject": "Founders Office Internship note"}, at("2026-09-14T22:30"))
    assert data["drafts"]["opp_1"]["status"] == "to_review"
    assert data["drafts"]["opp_1"]["approval_hash"] is None
    with pytest.raises(store.DraftError):
        store.edit_draft(data, "opp_1", {"status": "sent"}, at("2026-09-14T22:31"))


def test_due_for_send_only_returns_untouched_approvals_at_their_slot() -> None:
    data = store.empty()
    store.submit_drafts(data, "run_a", [submitted("a"), submitted("b"), submitted("c")], at("2026-09-14T20:00"))
    for lead_id in ("a", "b", "c"):
        store.approve(data, lead_id, at("2026-09-14T21:00"))
    data["drafts"]["b"]["body"] += " tampered"  # changed without going through edit_draft
    store.reject(data, "c", at("2026-09-14T21:30"))
    assert store.due_for_send(data, at("2026-09-15T09:59")) == []
    assert [d["lead_id"] for d in store.due_for_send(data, at("2026-09-15T10:00"))] == ["a"]
    store.mark_sent(data, "a", "gmail-1", at("2026-09-15T10:00"))
    assert store.due_for_send(data, at("2026-09-15T10:05")) == []
    assert data["drafts"]["a"]["status"] == "sent"
    with pytest.raises(store.DraftError):
        store.edit_draft(data, "a", {"subject": "late change here"}, at("2026-09-15T10:06"))


def test_save_and_load_round_trip(tmp_path) -> None:
    path = tmp_path / "outreach.json"
    data = store.load(path)
    store.submit_drafts(data, "run_a", [submitted()], at("2026-09-14T20:00"))
    store.save(path, data)
    assert store.load(path)["drafts"]["opp_1"]["status"] == "to_review"
