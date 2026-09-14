"""Send the cold emails Daksh approved, at their slot, exactly as approved.

Deterministic. Gmail, the attachment reader, persistence and sleep are passed
in so the send loop is testable without a network. Shadow mode sends Daksh a
copy addressed to himself instead of contacting the recipient.
Plan: internship workspace tasks/2026-09-approved-outreach-sender/plan.md.
"""

from __future__ import annotations

import base64
import json
import os
import random
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

import outreach_store as store

DAILY_CAP = 10
RESUME_DIR = Path(os.getenv("RESUME_DIR", "/data/resumes"))


def build_message(draft: dict[str, Any], sender: str, pdf: bytes, shadow_to: str | None) -> EmailMessage:
    message = EmailMessage()
    recipient = str(draft["to"])
    message["From"] = sender
    message["To"] = shadow_to or recipient
    message["Subject"] = (f"[SHADOW to {recipient}] " if shadow_to else "") + str(draft["subject"])
    message["X-Rise-Lead"] = str(draft["lead_id"])
    body = str(draft["body"])
    if shadow_to:
        body = (
            "Shadow mode: this is exactly what would have gone to "
            f"{recipient} ({draft.get('company')}). Nothing was sent to them.\n\n{body}"
        )
    message.set_content(body)
    message.add_attachment(pdf, maintype="application", subtype="pdf", filename=str(draft["attachment"]))
    return message


def send_due(
    data: dict[str, Any],
    now: datetime,
    *,
    send: Callable[[EmailMessage], str],
    read_attachment: Callable[[str], bytes],
    persist: Callable[[], None],
    sender: str,
    shadow_to: str | None,
    cap: int = DAILY_CAP,
    sleep: Callable[[float], None],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, draft in enumerate(store.due_for_send(data, now)[:cap]):
        lead_id = draft["lead_id"]
        if index:
            sleep(random.uniform(45, 90))  # ponytail: fixed jitter, tune if Gmail throttles
        store.mark_sending(data, lead_id, now)
        persist()  # before Gmail: a crash after this can never resend
        try:
            message = build_message(draft, sender, read_attachment(str(draft["attachment"])), shadow_to)
            message_id = send(message)
        except Exception as exc:  # noqa: BLE001 - one failure must not stop the rest
            store.mark_failed(data, lead_id, f"{type(exc).__name__}: {exc}", now)
            persist()
            results.append({"lead_id": lead_id, "status": "send_failed", "to": draft["to"], "error": str(exc)[:300]})
            continue
        if shadow_to:
            draft["status"] = "shadow_sent"
            draft["message_id"] = message_id
            draft.setdefault("history", []).append({"at": now.isoformat(), "event": "shadow_sent"})
        else:
            store.mark_sent(data, lead_id, message_id, now)
        persist()
        results.append({"lead_id": lead_id, "status": draft["status"], "message_id": message_id, "to": draft["to"]})
    return results


def report_body(results: list[dict[str, Any]], shadow: bool) -> str:
    lines = [f"Approved outreach send report{' (shadow mode)' if shadow else ''}", ""]
    if not results:
        lines.append("Nothing was due at this slot.")
    for item in results:
        detail = item.get("message_id") or item.get("error") or ""
        lines.append(f"- {item['status']}: {item.get('to')} ({item['lead_id']}) {detail}")
    return "\n".join(lines)


def gmail_sender() -> Callable[[EmailMessage], str]:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_authorized_user_info(json.loads(os.environ["GMAIL_TOKEN_JSON"]))
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def send(message: EmailMessage) -> str:
        del message["X-Rise-Lead"]
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        return str(service.users().messages().send(userId="me", body={"raw": raw}).execute()["id"])

    return send


def run_slot(commit: Callable[[], None] = lambda: None, now: datetime | None = None) -> dict[str, Any]:
    """Entry point for the 10:00 IST Modal function.

    OUTREACH_SEND_MODE: "off" sends nothing, "shadow" (default) mails Daksh the
    copies, "live" mails the approved recipients."""
    from digest import send_self_digest
    from sheets import record_outreach_sends
    from state import LocalState

    mode = os.getenv("OUTREACH_SEND_MODE", "shadow").strip().casefold()
    if mode not in {"shadow", "live"}:
        return {"status": "off", "results": []}
    sender = os.environ["OUTREACH_FROM"]
    state_dir = Path(os.getenv("PIPELINE_STATE_DIR", "/data/state"))
    path = state_dir / "outreach.json"
    data = store.load(path)
    now = now or datetime.now(store.IST)

    def persist() -> None:
        store.save(path, data)
        commit()

    results = send_due(
        data,
        now,
        send=gmail_sender(),
        read_attachment=read_resume,
        persist=persist,
        sender=sender,
        shadow_to=sender if mode == "shadow" else None,
        sleep=time.sleep,
    )
    sent = [data["drafts"][item["lead_id"]] for item in results if item["status"] == "sent"]
    sheet = {"status": "not_needed"}
    if sent:
        local = LocalState(state_dir / "state.json")
        payload = local.load()
        payload["sent_opportunity_ids"] = sorted(
            {*map(str, payload.get("sent_opportunity_ids", [])), *(d["lead_id"] for d in sent)}
        )
        local.save(payload)
        commit()
        try:
            sheet = record_outreach_sends(sent)
        except Exception as exc:  # noqa: BLE001 - the email is out; the Sheet can be fixed by hand
            sheet = {"status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    if results:
        send_self_digest(
            f"{'[SHADOW] ' if mode == 'shadow' else ''}{len(results)} approved email(s) processed - Rise",
            report_body(results, shadow=mode == "shadow") + f"\n\nSheet: {sheet}",
        )
    return {"status": mode, "results": results, "sheet": sheet}


def read_resume(name: str) -> bytes:
    path = (RESUME_DIR / name).resolve()
    if path.parent != RESUME_DIR.resolve():
        raise FileNotFoundError(name)
    return path.read_bytes()
