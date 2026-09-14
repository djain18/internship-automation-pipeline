"""Deterministic gate for a drafted cold email before it reaches Daksh's review page.

The Claude routine that writes drafts runs this on every draft
(`python personal_hunt/execution/check_draft.py drafts.json`) and the private
API runs it again on submit and on every edit. The prose checks are
validate_outreach's own humanizer rules; this adds the email-only rules from
EMAIL_COPY_RULES (tasks/2026-09-approved-outreach-sender/plan.md).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from models import clean_text
from outreach import validate_outreach

BODY_MIN_WORDS = 50
BODY_MAX_WORDS = 100
RESUME_ATTACHMENTS = frozenset(
    f"Daksh-Jain-{name}.pdf"
    for name in ("founders_office", "ai_automation", "gtm", "ops", "Master")
)
ENTERED_BY_DAKSH = "entered_by_daksh"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
# Numbers that read as achievement claims. candidate-profile.md keeps every such
# figure out of outreach until Daksh confirms its evidence.
_METRIC = re.compile(
    r"\d+(?:\.\d+)?\s*%|\d+\s*\+|\d+\s*x\b|\d+\s*(?:percent|leads|users|customers|hours|clients)\b",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    return clean_text(text).replace("’", "'").casefold()


def check_email_draft(draft: dict[str, Any]) -> list[str]:
    """Error codes for one draft; an empty list means it may go to review."""
    subject = clean_text(draft.get("subject"))
    body = str(draft.get("body") or "")
    errors = [
        error
        for error in validate_outreach(
            {"email_subject": subject, "linkedin_message": body, "send_status": "draft_needs_human_review"}
        )
        if error != "invalid_send_status"
    ]

    words = len(re.findall(r"[\w'’-]+", body))
    if words < BODY_MIN_WORDS:
        errors.append(f"body_too_short:{words}")
    if words > BODY_MAX_WORDS:
        errors.append(f"body_too_long:{words}")

    listing_subject = clean_text(draft.get("listing_subject"))
    if listing_subject:
        if _fold(subject) != _fold(listing_subject):
            errors.append("subject_ignores_listing_instruction")
    else:
        if subject != subject.lower():
            errors.append("subject_not_lowercase")
        count = len(subject.split())
        if not 2 <= count <= 4:
            errors.append(f"subject_word_count:{count}")
    if re.match(r"^(re|fwd?)\s*:", subject, re.IGNORECASE):
        errors.append("subject_fake_reply_prefix")

    if _METRIC.search(body):
        errors.append("unverified_metric")
    links = re.findall(r"https?://\S+", body)
    if len(links) > 1:
        errors.append(f"too_many_links:{len(links)}")

    if clean_text(draft.get("attachment")) not in RESUME_ATTACHMENTS:
        errors.append("attachment_not_allowed")

    recipient = clean_text(draft.get("to"))
    if recipient:
        if not _EMAIL.match(recipient):
            errors.append("recipient_invalid")
        source = clean_text(draft.get("to_source"))
        if not (source == ENTERED_BY_DAKSH or source.startswith(("http://", "https://"))):
            errors.append("recipient_missing_source")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_draft.py drafts.json", file=sys.stderr)
        return 2
    drafts = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    report = {str(item.get("lead_id")): check_email_draft(item) for item in drafts}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if any(report.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
