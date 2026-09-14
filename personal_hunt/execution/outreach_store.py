"""State for approved cold emails: drafts, approvals, send slots, sends.

One JSON document at state/outreach.json on the Modal volume, keyed by lead
id so a lead is drafted, approved and sent at most once. Pure functions over
that document; the private API and the sender load, change and save it.
Plan: internship workspace tasks/2026-09-approved-outreach-sender/plan.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from check_draft import ENTERED_BY_DAKSH, check_email_draft
from models import clean_text

IST = ZoneInfo("Asia/Kolkata")
SEND_TIME = time(10, 0)  # Belkins 2026: 8 AM-noon replies best; see plan section 1
LOCK_TIME = time(9, 0)
EDITABLE = ("to", "to_source", "subject", "body", "attachment")
DRAFT_FIELDS = (*EDITABLE, "listing_subject", "follow_up", "linkedin_note", "notes")
REPLACEABLE = {"to_review", "needs_address", "blocked_validation"}
FINAL = {"sent", "sending"}

Record = dict[str, Any]


class DraftError(ValueError):
    """A request the draft's current state does not allow."""


def empty() -> Record:
    return {"drafts": {}}


def load(path: Path) -> Record:
    if not path.is_file():
        return empty()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("drafts", {})
    return data


def save(path: Path, data: Record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def next_send_slot(approved_at: datetime) -> datetime:
    """The first weekday 10:00 IST whose 09:00 lock is still ahead."""
    local = approved_at.astimezone(IST)
    day = local.date()
    if local.time() >= LOCK_TIME:
        day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, SEND_TIME, tzinfo=IST)


def approval_hash(draft: Record) -> str:
    payload = "\x1f".join(clean_text(draft.get(key)) for key in ("to", "subject", "attachment"))
    payload += "\x1f" + str(draft.get("body") or "")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def drafting_queue(run: Record, data: Record, sent_ids: set[str]) -> list[Record]:
    """Approved leads from the run that still need a draft, with what the routine needs."""
    queue: list[Record] = []
    for item in list(run.get("digest_primary") or []) + list(run.get("digest_remote_fallback") or []):
        lead_id = str(item.get("id") or "")
        if not lead_id or lead_id in sent_ids:
            continue
        existing = data["drafts"].get(lead_id)
        if existing and existing.get("status") not in {"blocked_validation"}:
            continue
        contact = item.get("selected_contact") or {}
        queue.append(
            {
                "lead_id": lead_id,
                "company": item.get("company"),
                "title": item.get("title"),
                "source_url": item.get("source_url"),
                "apply_url": item.get("apply_url"),
                "kimi_fit": item.get("llm_fit_score"),
                "attachment": f"{clean_text(item.get('resume')) or 'Daksh-Jain-Master'}.pdf",
                "contact": {
                    "email": clean_text(contact.get("email")) or None,
                    "source": clean_text(contact.get("source_url")) or None,
                },
                "listing_text": str(item.get("listing_page_text") or item.get("description") or "")[:6000],
                "prompt": (item.get("outreach") or {}).get("claude_prompt") or "",
            }
        )
    return queue


def _status_for(draft: Record) -> str:
    if draft["errors"]:
        return "blocked_validation"
    return "to_review" if clean_text(draft.get("to")) else "needs_address"


def _stamp(draft: Record, event: str, now: datetime) -> None:
    draft["updated_at"] = now.isoformat()
    draft.setdefault("history", []).append({"at": now.isoformat(), "event": event})


def submit_drafts(data: Record, run_id: str, drafts: list[Record], now: datetime) -> dict[str, str]:
    """Store routine drafts. Never overwrites a draft Daksh approved, rejected or sent."""
    result: dict[str, str] = {}
    for incoming in drafts:
        lead_id = clean_text(incoming.get("lead_id"))
        if not lead_id:
            continue
        current = data["drafts"].get(lead_id)
        if current and current.get("status") not in REPLACEABLE:
            result[lead_id] = current["status"]
            continue
        draft = {**(current or {}), "lead_id": lead_id, "run_id": run_id}
        for key in DRAFT_FIELDS:
            draft[key] = incoming.get(key)
        for key in ("company", "title", "source_url", "kimi_fit"):
            if incoming.get(key) is not None:
                draft[key] = incoming.get(key)
        draft["errors"] = check_email_draft(draft)
        draft["approval_hash"] = None
        draft["status"] = _status_for(draft)
        _stamp(draft, "drafted", now)
        data["drafts"][lead_id] = draft
        result[lead_id] = draft["status"]
    return result


def _get(data: Record, lead_id: str) -> Record:
    draft = data["drafts"].get(lead_id)
    if draft is None:
        raise DraftError("unknown draft")
    return draft


def edit_draft(data: Record, lead_id: str, changes: Record, now: datetime) -> Record:
    draft = _get(data, lead_id)
    if draft.get("status") in FINAL:
        raise DraftError("a sent email cannot be edited")
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise DraftError(f"not editable: {', '.join(sorted(unknown))}")
    if "to" in changes and clean_text(changes["to"]) != clean_text(draft.get("to")) and "to_source" not in changes:
        changes = {**changes, "to_source": ENTERED_BY_DAKSH if clean_text(changes["to"]) else ""}
    draft.update(changes)
    draft["errors"] = check_email_draft(draft)
    draft["approval_hash"] = None
    draft["slot"] = None
    draft["status"] = _status_for(draft)
    _stamp(draft, "edited", now)
    return draft


def approve(data: Record, lead_id: str, now: datetime) -> Record:
    draft = _get(data, lead_id)
    if draft.get("status") != "to_review":
        raise DraftError(f"cannot approve a draft that is {draft.get('status')}")
    if check_email_draft(draft):
        raise DraftError("draft fails its checks")
    draft["status"] = "approved"
    draft["approval_hash"] = approval_hash(draft)
    draft["approved_at"] = now.isoformat()
    draft["slot"] = next_send_slot(now).isoformat()
    _stamp(draft, "approved", now)
    return draft


def reject(data: Record, lead_id: str, now: datetime) -> Record:
    draft = _get(data, lead_id)
    if draft.get("status") in FINAL:
        raise DraftError("a sent email cannot be rejected")
    draft["status"] = "rejected"
    draft["approval_hash"] = None
    draft["slot"] = None
    _stamp(draft, "rejected", now)
    return draft


def due_for_send(data: Record, now: datetime) -> list[Record]:
    """Approved drafts whose slot has come and whose content is exactly what was approved."""
    due = [
        draft
        for draft in data["drafts"].values()
        if draft.get("status") == "approved"
        and draft.get("slot")
        and datetime.fromisoformat(draft["slot"]) <= now
        and clean_text(draft.get("to"))
        and draft.get("approval_hash") == approval_hash(draft)
        and not check_email_draft(draft)
    ]
    return sorted(due, key=lambda draft: (-(draft.get("kimi_fit") or 0), draft["lead_id"]))


def mark_sending(data: Record, lead_id: str, now: datetime) -> None:
    draft = _get(data, lead_id)
    draft["status"] = "sending"
    _stamp(draft, "sending", now)


def mark_sent(data: Record, lead_id: str, message_id: str, now: datetime) -> None:
    draft = _get(data, lead_id)
    draft["status"] = "sent"
    draft["message_id"] = message_id
    draft["sent_at"] = now.isoformat()
    _stamp(draft, "sent", now)


def mark_failed(data: Record, lead_id: str, error: str, now: datetime) -> None:
    draft = _get(data, lead_id)
    draft["status"] = "send_failed"
    draft["send_error"] = error[:300]
    _stamp(draft, "send_failed", now)
