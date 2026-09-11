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

STRATEGY_RULES = (
    ("growth_funnel_teardown", ("growth", "conversion", "funnel", "acquisition", "retention")),
    ("launch_checklist", ("launch", "go-to-market", "gtm", "rollout")),
    ("role_process_map", ("cross-functional", "stakeholder", "coordination", "process")),
    ("operations_workflow_audit", ("operations", "workflow", "automation", "manual", "ops")),
)


def choose_strategy(record: Record) -> str:
    """Choose a reproducible strategy from cited research, never from invention."""
    research = record.get("research") if isinstance(record.get("research"), dict) else {}
    evidence = research.get("evidence") or research.get("claims") or []
    parts = [clean_text(research.get("primary_responsibility")), clean_text(research.get("solution_concept"))]
    for item in evidence:
        if isinstance(item, dict) and item.get("source_url"):
            parts.append(clean_text(item.get("claim") or item.get("observation")))
    haystack = " ".join(parts).casefold()
    for strategy_id, keywords in STRATEGY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return strategy_id
    return "role_process_map"


def _approved_artifact(record: Record) -> str:
    if not record.get("artifact_human_approved"):
        return ""
    return clean_text(record.get("artifact_public_url") or record.get("artifact_path"))


def _followups(record: Record, company: str) -> list[Record]:
    research = record.get("research") if isinstance(record.get("research"), dict) else {}
    candidates = research.get("followup_evidence") or []
    by_day = {item.get("day"): item for item in candidates if isinstance(item, dict)}
    output: list[Record] = []
    for day in (3, 8):
        item = by_day.get(day) or {}
        observation = clean_text(item.get("observation") or item.get("value"))
        source_url = clean_text(item.get("source_url"))
        if not observation or not source_url or not item.get("access_date") or not item.get("confidence"):
            output.append({"day": day, "status": "suppressed_no_new_cited_value"})
            continue
        output.append({
            "day": day,
            "status": "draft_needs_human_review",
            "source_url": source_url,
            "access_date": item["access_date"],
            "confidence": item["confidence"],
            "body": f"One useful update since my note about {company}: {observation} Source: {source_url}",
        })
    output.append({
        "day": 14,
        "status": "draft_needs_human_review",
        "angle": "close_loop",
        "body": f"I'll close the loop here. If the {company} idea is relevant, I’m happy to share an outline; otherwise, no action needed.",
    })
    return output


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
    strategy_id = choose_strategy(record)
    artifact = _approved_artifact(record)
    opening = (
        f"your {title} listing in {location} asks for someone to "
        f"{_clause(problem)}"
        if problem
        else f"your {title} opening in {location} pairs hands-on execution with a "
        f"broad view of {company}"
    )
    resource_phrase = f" I can share the approved resource: {artifact}." if artifact else ""
    body = (
        f"Hi {contact_name}, {opening}. I mapped the public context into a "
        f"source-linked brief and one small idea: {solution} My background spans "
        "founder's-office automation, D2C operations, growth, and internal tools "
        "while I study at Christ University in Bengaluru. I'm looking for a "
        "six-month onsite generalist internship in Bengaluru from November 2026 "
        f"where I can own work across functions.{resource_phrase} Would a short outline be useful?"
    )
    # A long company name plus a long title pushed one real draft to 303
    # characters, so the note is built short and then held under the limit.
    linkedin = (
        f"Hi {contact_name} - the {title} work at {company} caught my attention. "
        "I mapped the public context into a short evidence brief and one small "
        "idea. I'm seeking a six-month Bengaluru generalist internship from "
        "November 2026. Useful if I share it?"
    )
    if len(linkedin) > 300:
        linkedin = (
            f"Hi {contact_name} - the {title} work at {company} caught my "
            "attention. I mapped the public context into a short brief and one "
            "idea. Seeking a six-month Bengaluru internship from November 2026. "
            "Share it?"
        )[:300]
    followups = _followups(record, company)
    if not solution:
        return {
            "subject": "founder office idea",
            "email_body": "",
            "linkedin_note": linkedin,
            "followups": followups,
            "send_status": "blocked_insufficient_evidence",
            "artifact_mention_allowed": False,
            "strategy_id": strategy_id,
        }
    return {
        "subject": "founder office idea",
        "email_body": body,
        "linkedin_note": linkedin,
        "followups": followups,
        "send_status": "draft_needs_human_review",
        "artifact_mention_allowed": bool(artifact),
        "strategy_id": strategy_id,
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

