import base64
from datetime import datetime
from email import message_from_bytes
from pathlib import Path
from zoneinfo import ZoneInfo

import digest
import outreach_store as store
import pipeline
from state import LocalState

from .test_digest_html import _run
from .test_outreach_store import submitted

IST = ZoneInfo("Asia/Kolkata")


def _review_run():
    run = _run()
    run["run_id"] = "run_a"
    run["outreach_next_slot"] = "2026-09-15T10:00:00+05:30"
    run["outreach_drafts"] = [
        {**submitted("a"), "company": "Auraaison <AI>", "status": "to_review", "errors": []},
        {**submitted("b", to=None, to_source=""), "company": "Kplor", "status": "needs_address", "errors": []},
        {**submitted("c"), "company": "Koyo", "status": "blocked_validation", "errors": ["body_too_long:140"]},
    ]
    return run


def test_html_review_section_lists_every_draft_escaped() -> None:
    html_body = digest.render_html_digest(_review_run())
    assert "3 emails to approve by 09:00" in html_body
    assert "Auraaison &lt;AI&gt;" in html_body and "Auraaison <AI>" not in html_body
    assert "admin@auraaison.com" in html_body
    assert "Daksh-Jain-founders_office.pdf" in html_body
    assert "needs an address" in html_body
    assert "body_too_long:140" in html_body
    assert "/my-hunt/outbox" in html_body
    assert "Tue 15 Sep, 10:00 IST" in html_body


def test_text_review_section() -> None:
    text = digest.render_digest(_review_run())
    assert "## 3 emails to approve by 09:00" in text
    assert "Subject: founder office intern" in text
    assert "To: needs an address" in text


def test_no_review_section_without_drafts() -> None:
    assert "to approve by 09:00" not in digest.render_html_digest(_run())


def test_send_self_digest_attaches_files(monkeypatch) -> None:
    captured = {}

    class Service:
        def users(self):
            return self

        def messages(self):
            return self

        def send(self, **kwargs):
            captured.update(kwargs)
            return self

        def execute(self):
            return {"id": "gmail-2"}

    monkeypatch.setenv("GMAIL_TOKEN_JSON", '{"token":"x","refresh_token":"r","token_uri":"https://oauth2.googleapis.com/token","client_id":"c","client_secret":"s"}')
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshjainn02@gmail.com")
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *_a, **_k: Service())
    digest.send_self_digest("S", "Plain", "<b>h</b>", attachments=[("Daksh-Jain-gtm.pdf", b"%PDF")])
    parsed = message_from_bytes(base64.urlsafe_b64decode(captured["body"]["raw"]))
    assert [p.get_filename() for p in parsed.walk() if p.get_filename()] == ["Daksh-Jain-gtm.pdf"]


def test_attach_outreach_review_reads_this_runs_reviewable_drafts(tmp_path: Path) -> None:
    data = store.empty()
    store.submit_drafts(data, "run_a", [submitted("a"), submitted("b", to=None, to_source="")], datetime(2026, 9, 14, 20, tzinfo=IST))
    store.submit_drafts(data, "run_old", [submitted("old")], datetime(2026, 9, 13, 20, tzinfo=IST))
    store.approve(data, "a", datetime(2026, 9, 14, 20, 30, tzinfo=IST))
    store.save(tmp_path / "outreach.json", data)
    run = {"run_id": "run_a"}
    pipeline.attach_outreach_review(run, tmp_path, datetime(2026, 9, 14, 21, tzinfo=IST))
    assert [d["lead_id"] for d in run["outreach_drafts"]] == ["b"]
    assert run["outreach_next_slot"] == "2026-09-15T10:00:00+05:30"


def test_review_email_still_sends_after_the_same_days_plain_digest(monkeypatch, tmp_path: Path) -> None:
    # 2026-09-14: the day's digest had already gone out, so the 21:00 run with
    # drafts would have been skipped as "already sent" and no review email sent.
    subjects = []

    def fake_send(subject, _body, _html="", attachments=None):
        subjects.append(subject)
        return f"gmail-{len(subjects)}"

    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshjainn02@gmail.com")
    monkeypatch.setenv("RESUME_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "send_self_digest", fake_send)
    monkeypatch.setattr(pipeline, "_ist_delivery_key", lambda run_id: f"2026-09-14:{run_id}")
    state = LocalState(tmp_path / "state.json")
    plain = {**_run(), "run_id": "run_a", "run_kind": "live", "digest_usable": True}
    assert pipeline._send_once(plain, state)[0].startswith("digest_sent")
    review = {**_review_run(), "run_kind": "live", "digest_usable": True}
    assert pipeline._send_once(review, state)[0] != "digest_already_sent"
    assert pipeline._send_once(review, state)[0] == "digest_already_sent"
    assert len(subjects) == 2


def test_send_once_attaches_resumes_and_prefixes_subject(monkeypatch, tmp_path: Path) -> None:
    sent = {}

    def fake_send(subject, _body, _html="", attachments=None):
        sent.update(subject=subject, attachments=attachments)
        return "gmail-3"

    resumes = tmp_path / "resumes"
    resumes.mkdir()
    (resumes / "Daksh-Jain-founders_office.pdf").write_bytes(b"%PDF-1")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshjainn02@gmail.com")
    monkeypatch.setenv("RESUME_DIR", str(resumes))
    monkeypatch.setattr(pipeline, "send_self_digest", fake_send)
    run = {**_review_run(), "run_kind": "live", "digest_usable": True, "funding_primary": [], "funding_extended": []}
    pipeline._send_once(run, LocalState(tmp_path / "state.json"))
    assert sent["subject"].startswith("[3 to approve by 09:00] ")
    assert sent["attachments"] == [("Daksh-Jain-founders_office.pdf", b"%PDF-1")]
