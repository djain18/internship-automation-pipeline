from __future__ import annotations

import re
from models import Record, clean_text


FORBIDDEN_PHRASES = (
    "i hope this email finds you well",
    "just checking in",
    "bumping this",
    "synergy",
    "best-in-class",
)


def _words(text: str) -> list[str]:
    return re.findall(r"\b[\w’'-]+\b", text)


def _recipient(record: Record) -> str:
    contact = record.get("selected_contact", {})
    return clean_text(contact.get("name")) or "there"


def draft_outreach(record: Record) -> Record:
    company = clean_text(record.get("company"))
    title = clean_text(record.get("title"))
    location = clean_text(record.get("location")) or "Bengaluru"
    contact_name = _recipient(record)
    research = record.get("research", {})
    solution = clean_text(research.get("solution_concept"))
    body = (
        f"Hi {contact_name}, your {title} opening in {location} stood out because it "
        f"combines hands-on execution with a broad view of {company}. I mapped the "
        f"public information around the role into a source-linked brief and outlined "
        f"one small idea: {solution} My background spans founder's-office automation, "
        "D2C operations, growth, and internal tools while I study at Christ University "
        "in Bengaluru. I'm looking for a six-month onsite generalist internship from "
        "November 2026 where I can own work across functions. Would the brief be useful "
        "for a quick look?"
    )
    linkedin = (
        f"Hi {contact_name} - the {title} work at {company} caught my attention. I mapped "
        "the public context into a short evidence brief and one small solution idea. "
        "I'm seeking a six-month Bengaluru Founder’s Office/generalist internship from "
        "November 2026. Useful if I share it?"
    )
    followups = [
        {
            "day": 3,
            "angle": "new evidence",
            "body": (
                f"One addition since my note: I separated what is publicly observed at "
                f"{company} from what still needs validation. I can send that one-page "
                "evidence map if it would save you time reviewing the idea."
            ),
        },
        {
            "day": 8,
            "angle": "implementation",
            "body": (
                f"I also reduced the {company} idea to a smallest-test version with a "
                "human approval gate and no assumed outcome. Worth sending the test plan?"
            ),
        },
        {
            "day": 14,
            "angle": "close loop",
            "body": (
                f"I'll close the loop after this. The most useful takeaway was that "
                f"{research.get('uncertainty', 'the internal workflow needs validation')} "
                "If that is relevant, I’m happy to share the brief; otherwise, no action needed."
            ),
        },
    ]
    return {
        "subject": "founder office idea",
        "email_body": body,
        "linkedin_note": linkedin,
        "followups": followups,
        "send_status": "draft_needs_human_review",
        "artifact_mention_allowed": record.get("artifact_status") == "verified",
    }


def validate_outreach(draft: Record) -> list[str]:
    errors: list[str] = []
    subject = clean_text(draft.get("subject"))
    body = clean_text(draft.get("email_body"))
    linkedin = clean_text(draft.get("linkedin_note"))
    word_count = len(_words(body))
    if not 80 <= word_count <= 110:
        errors.append(f"email_word_count:{word_count}")
    if not 2 <= len(_words(subject)) <= 4 or subject != subject.casefold():
        errors.append("subject_format")
    if len(linkedin) > 300:
        errors.append(f"linkedin_too_long:{len(linkedin)}")
    lowered = f"{subject} {body}".casefold()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            errors.append(f"forbidden_phrase:{phrase}")
    url_count = len(re.findall(r"https?://", body))
    if url_count > 1:
        errors.append("too_many_links")
    if draft.get("send_status") not in {"draft_needs_human_review", "approved_manual_send"}:
        errors.append("invalid_send_status")
    return errors

