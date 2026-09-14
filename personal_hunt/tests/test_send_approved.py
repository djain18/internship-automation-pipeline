from datetime import datetime
from email import message_from_bytes
from zoneinfo import ZoneInfo

import outreach_store as store
import send_approved

from .test_outreach_store import submitted

IST = ZoneInfo("Asia/Kolkata")
SLOT = datetime(2026, 9, 15, 10, 0, tzinfo=IST)


def approved_store(*lead_ids):
    data = store.empty()
    store.submit_drafts(data, "run_a", [submitted(lead_id, to=f"{lead_id}@example.com") for lead_id in lead_ids],
                        datetime(2026, 9, 14, 20, 0, tzinfo=IST))
    for lead_id in lead_ids:
        store.approve(data, lead_id, datetime(2026, 9, 14, 21, 0, tzinfo=IST))
    return data


class Recorder:
    def __init__(self, fail_for=()):
        self.messages = []
        self.persisted = []
        self.fail_for = set(fail_for)

    def send(self, message):
        if message["X-Rise-Lead"] in self.fail_for:
            raise RuntimeError("gmail 500")
        self.messages.append(message)
        return f"gmail-{len(self.messages)}"


def attachment(_name):
    return b"%PDF-1.4 resume"


def run_sender(data, recorder, **kwargs):
    return send_approved.send_due(
        data,
        SLOT,
        send=recorder.send,
        read_attachment=kwargs.pop("read_attachment", attachment),
        persist=lambda: recorder.persisted.append({k: v["status"] for k, v in data["drafts"].items()}),
        sender="dakshjainn02@gmail.com",
        sleep=lambda _s: None,
        **kwargs,
    )


def test_message_is_plain_text_with_the_resume_attached() -> None:
    data = approved_store("a")
    recorder = Recorder()
    results = run_sender(data, recorder, shadow_to=None)
    assert results == [{"lead_id": "a", "status": "sent", "message_id": "gmail-1", "to": "a@example.com"}]
    message = message_from_bytes(recorder.messages[0].as_bytes())
    assert message["To"] == "a@example.com"
    assert message["From"] == "dakshjainn02@gmail.com"
    assert message["Subject"] == "founder office intern"
    parts = list(message.walk())
    assert [p.get_content_type() for p in parts] == ["multipart/mixed", "text/plain", "application/pdf"]
    assert parts[2].get_filename() == "Daksh-Jain-founders_office.pdf"
    assert data["drafts"]["a"]["status"] == "sent"
    # State is saved as "sending" before Gmail is called, so a crash can never resend.
    assert recorder.persisted[0]["a"] == "sending"


def test_nothing_is_sent_twice() -> None:
    data = approved_store("a")
    recorder = Recorder()
    run_sender(data, recorder, shadow_to=None)
    assert run_sender(data, recorder, shadow_to=None) == []
    assert len(recorder.messages) == 1


def test_shadow_mode_sends_to_daksh_and_never_to_the_recipient() -> None:
    data = approved_store("a")
    recorder = Recorder()
    results = run_sender(data, recorder, shadow_to="dakshjainn02@gmail.com")
    message = recorder.messages[0]
    assert message["To"] == "dakshjainn02@gmail.com"
    assert message["Subject"].startswith("[SHADOW to a@example.com]")
    assert results[0]["status"] == "shadow_sent"
    assert data["drafts"]["a"]["status"] == "shadow_sent"
    assert run_sender(data, recorder, shadow_to="dakshjainn02@gmail.com") == []


def test_daily_cap_and_failures_do_not_block_the_rest() -> None:
    data = approved_store("a", "b", "c")
    recorder = Recorder(fail_for={"a"})
    results = run_sender(data, recorder, shadow_to=None, cap=2)
    assert [(r["lead_id"], r["status"]) for r in results] == [("a", "send_failed"), ("b", "sent")]
    assert data["drafts"]["c"]["status"] == "approved"
    assert "gmail 500" in data["drafts"]["a"]["send_error"]


def test_missing_attachment_fails_without_sending() -> None:
    data = approved_store("a")
    recorder = Recorder()

    def missing(_name):
        raise FileNotFoundError("no resume")

    results = run_sender(data, recorder, shadow_to=None, read_attachment=missing)
    assert results[0]["status"] == "send_failed"
    assert recorder.messages == []


def test_sheet_records_sends_on_existing_and_new_rows() -> None:
    from sheets import TAB_SCHEMAS, outreach_send_updates

    headers = TAB_SCHEMAS["Outreach"]
    existing = [""] * len(headers)
    existing[0] = "outreach_a"
    sends = [
        {"lead_id": "a", "to": "a@example.com", "subject": "founder office intern", "message_id": "g1",
         "sent_at": "2026-09-15T10:00:00+05:30"},
        {"lead_id": "b", "to": "b@example.com", "subject": "gtm intern note", "message_id": "g2",
         "sent_at": "2026-09-15T10:01:00+05:30", "company": "BCo"},
    ]
    updates, appended = outreach_send_updates([headers, existing], sends)
    by_range = {u["range"]: u["values"][0][0] for u in updates}
    sent_at_col = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[headers.index("sent_at")]
    assert by_range[f"'Outreach'!{sent_at_col}2"] == "2026-09-15"
    assert "sent_after_approval" in by_range.values()
    assert len(appended) == 1
    assert appended[0][headers.index("id")] == "outreach_b"
    assert appended[0][headers.index("outcome_basis")] == "gmail_message:g2"


def test_report_lists_every_result() -> None:
    body = send_approved.report_body(
        [
            {"lead_id": "a", "status": "sent", "to": "a@example.com", "message_id": "gmail-1"},
            {"lead_id": "b", "status": "send_failed", "to": "b@example.com", "error": "gmail 500"},
        ],
        shadow=False,
    )
    assert "a@example.com" in body and "gmail 500" in body
