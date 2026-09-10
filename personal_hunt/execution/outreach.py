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


def _clause(problem: str) -> str:
    """Trim the quoted responsibility to a clause an email can carry."""

    text = clean_text(problem).lstrip("-").strip()
    for prefix in ("You will ", "you will ", "Role: ", "- Role: "):
        text = text.removeprefix(prefix)
    words = text.split()
    clause = " ".join(words[:14])
    if len(words) > 14 and "," in clause:
        # Cutting at a word boundary left "...shaping new products across."
        clause = clause[: clause.rfind(",")]
    return clause.rstrip(".,;:").casefold()


def _recipient(record: Record) -> str:
    contact = record.get("selected_contact", {})
    name = clean_text(contact.get("name"))
    # Some sources put the company in the contact name field. "Hi Acme," reads
    # like a mail merge, which is exactly what this is trying not to be.
    if not name or name.casefold() == clean_text(record.get("company")).casefold():
        return "there"
    return name


def draft_outreach(record: Record) -> Record:
    company = clean_text(record.get("company"))
    title = clean_text(record.get("title"))
    location = clean_text(record.get("location")) or "Bengaluru"
    contact_name = _recipient(record)
    research = record.get("research", {})
    solution = clean_text(research.get("solution_concept"))
    # The observed problem is what makes the note specific; sending only the
    # solution was why every draft read the same. Quote the listing when it gave
    # one, and fall back to the role's own breadth when it did not.
    problem = clean_text(research.get("primary_responsibility"))
    opening = (
        f"your {title} listing in {location} asks for someone to "
        f"{_clause(problem)}"
        if problem
        else f"your {title} opening in {location} pairs hands-on execution with a "
        f"broad view of {company}"
    )
    body = (
        f"Hi {contact_name}, {opening}. I mapped the public context into a "
        f"source-linked brief and one small idea: {solution} My background spans "
        "founder's-office automation, D2C operations, growth, and internal tools "
        "while I study at Christ University in Bengaluru. I'm looking for a "
        "six-month onsite generalist internship in Bengaluru from November 2026 "
        "where I can own work across functions. Would the brief be useful?"
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
    if not solution:
        return {
            "subject": "founder office idea",
            "email_body": "",
            "linkedin_note": linkedin,
            "followups": followups,
            "send_status": "blocked_insufficient_evidence",
            "artifact_mention_allowed": False,
        }
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
    if draft.get("send_status") == "blocked_insufficient_evidence":
        return errors
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

