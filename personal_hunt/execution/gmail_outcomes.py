"""Fill the Sheet's Outreach outcome columns from Daksh's own Gmail.

Daksh asked (2026-09-13) not to type sent_at / reply_outcome /
interview_outcome by hand every day. This reads his mailbox with a
gmail.readonly token and writes what it can prove:

- sent_at + send_status=sent_manually: a message in Sent addressed to the
  row's contact_email, or, when the row has no contact email, a Sent message
  whose subject names the company.
- reply_outcome: a message from that address (or its domain) after sent_at.
  "rejected" when the reply uses a clear rejection phrase, "interview_requested"
  when it asks to schedule a call or interview, otherwise "replied".
- interview_outcome=invited: a Google Calendar invitation that mentions the
  contact's domain after sent_at.

It never overwrites a value Daksh typed. The one exception is send_status,
which the pipeline itself pre-fills with its draft status; that pipeline
value may be replaced by sent_manually. Every write records its evidence in
the outcome_basis column (the Gmail message id and how it matched), so a
wrong match is easy to spot and undo. Nothing is sent, labelled or deleted.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from email.utils import parseaddr
from typing import Any

from models import Record

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

# Values the pipeline writes into send_status itself. Anything else in that
# column was typed by Daksh and is left alone.
PIPELINE_SEND_STATUSES = {
    "", "draft_needs_human_review", "research_first_needs_human_review",
    "blocked_insufficient_evidence", "blocked_no_evidence", "blocked_validation",
    "approved_manual_send",
}
FREE_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "proton.me", "protonmail.com", "live.com", "rediffmail.com",
}
REJECTION_PHRASES = (
    "unfortunately", "not moving forward", "not be moving forward", "other candidates",
    "position has been filled", "role has been filled", "not a fit at this time",
    "decided to go with", "will not be proceeding", "won't be proceeding",
)
INTERVIEW_PHRASES = (
    "schedule a call", "schedule an interview", "set up a call", "hop on a call",
    "book a slot", "calendly.com", "cal.com/", "your availability", "interview round",
    "quick chat", "free for a call",
)


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].casefold() if "@" in email else ""


def _headers(message: Record) -> dict[str, str]:
    return {
        str(item.get("name", "")).casefold(): str(item.get("value", ""))
        for item in (message.get("payload") or {}).get("headers") or []
    }


def _message_date(message: Record) -> date | None:
    try:
        millis = int(message.get("internalDate"))
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date()


def classify_reply(text: str) -> str:
    lowered = text.casefold()
    if any(phrase in lowered for phrase in REJECTION_PHRASES):
        return "rejected"
    if any(phrase in lowered for phrase in INTERVIEW_PHRASES):
        return "interview_requested"
    return "replied"


class GmailSearch:
    """The three Gmail calls this module needs, behind one small seam so the
    matching logic is testable without a network."""

    def __init__(self, service: Any):
        self._messages = service.users().messages()

    def find(self, query: str, limit: int = 5) -> list[Record]:
        listed = self._messages.list(userId="me", q=query, maxResults=limit).execute()
        output = []
        for item in listed.get("messages") or []:
            output.append(
                self._messages.get(
                    userId="me", id=item["id"], format="metadata",
                    metadataHeaders=["From", "To", "Subject"],
                ).execute()
            )
        return output


def _oldest(messages: list[Record]) -> Record | None:
    dated = [(d, m) for m in messages if (d := _message_date(m)) is not None]
    return min(dated, key=lambda pair: pair[0])[1] if dated else None


def outcome_updates(rows: list[Record], search: Any, today: date) -> dict[str, Record]:
    """{outreach row id: {column: value}} for everything Gmail proves.

    A row is only considered when its column is still empty (send_status may
    hold a pipeline value). Searches are bounded to the last 60 days.
    """
    updates: dict[str, Record] = {}
    for row in rows:
        row_id = str(row.get("id") or "")
        if not row_id:
            continue
        email = str(row.get("contact_email") or "").strip().casefold()
        company = str(row.get("company") or "").strip()
        change: Record = {}
        basis: list[str] = []
        sent_at = str(row.get("sent_at") or "").strip()[:10]

        if not sent_at:
            if email:
                sent = _oldest(search.find(f"in:sent to:{email} newer_than:60d"))
                how = "sent_to_contact_email"
            elif company and len(company) >= 4:
                sent = _oldest(search.find(f'in:sent subject:"{company}" newer_than:60d'))
                how = "sent_subject_names_company"
            else:
                sent = None
            if sent is not None and (sent_day := _message_date(sent)) is not None:
                sent_at = sent_day.isoformat()
                change["sent_at"] = sent_at
                if not email:
                    email = parseaddr(_headers(sent).get("to", ""))[1].casefold()
                basis.append(f"{how}:{sent.get('id')}")
        if sent_at and str(row.get("send_status") or "").strip().casefold() in PIPELINE_SEND_STATUSES:
            change["send_status"] = "sent_manually"

        if sent_at and email:
            domain = _domain(email)
            reply_from = f"@{domain}" if domain and domain not in FREE_MAIL_DOMAINS else email
            after = sent_at.replace("-", "/")
            if not str(row.get("reply_outcome") or "").strip():
                replies = search.find(f"from:{reply_from} after:{after} -in:sent")
                reply = _oldest(replies)
                if reply is not None:
                    text = f"{_headers(reply).get('subject', '')} {reply.get('snippet', '')}"
                    change["reply_outcome"] = classify_reply(text)
                    basis.append(f"reply:{reply.get('id')}")
            if not str(row.get("interview_outcome") or "").strip() and domain not in FREE_MAIL_DOMAINS:
                invites = search.find(
                    f"from:calendar-notification@google.com subject:Invitation {domain} after:{after}"
                )
                invite = _oldest(invites)
                if invite is not None:
                    change["interview_outcome"] = "invited"
                    basis.append(f"calendar_invite:{invite.get('id')}")

        if change:
            existing = str(row.get("outcome_basis") or "").strip()
            change["outcome_basis"] = "; ".join(filter(None, [existing, *basis])) or existing
            updates[row_id] = change
    return updates


def gmail_read_service():
    """A Gmail client from GMAIL_OUTCOMES_TOKEN_JSON, or None when the
    read-only token has not been authorised yet."""
    import json

    raw = os.getenv("GMAIL_OUTCOMES_TOKEN_JSON", "").strip()
    if not raw:
        return None
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_authorized_user_info(json.loads(raw), [GMAIL_READ_SCOPE])
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)
