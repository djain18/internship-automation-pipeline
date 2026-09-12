from __future__ import annotations

import re
from models import Record, clean_text

# Humanizer rules - hard-fail checks for outreach quality
FORBIDDEN_PUNCTUATION = {
    "—": "em-dash",  # No em dashes
    "“": "curly-quote-open",  # No curly quotes
    "”": "curly-quote-close",
    "’": "curly-quote-single",  # Not the plain ASCII apostrophe (') --
    # that's what every real contraction ("I've", "don't") uses, and
    # flagging it would hard-fail nearly every natural-sounding draft.
}

FORBIDDEN_WORDS = (
    "delve",
    "leverage",
    "robust",
    "testament",
    "underscore",
    "showcase",
    "landscape",
    "pivotal",
    "crucial",
    "vibrant",
)

FORBIDDEN_PHRASES = (
    "i hope this email finds you well",
    "i hope this helps",
    "let me know",
    "just checking in",
    "bumping this",
    "synergy",
    "best-in-class",
    "world-class",
    "cutting-edge",
    "looking forward to",
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


def _is_problem_led_company(record: Record) -> bool:
    """Check if company has deep problem research and prompt generation."""
    deep_research = record.get("deep_problem_research") if isinstance(record.get("deep_problem_research"), dict) else {}
    prompt_gen = record.get("prompt_generation") if isinstance(record.get("prompt_generation"), dict) else {}
    return bool(deep_research.get("observed_signals") and prompt_gen.get("prompt_text"))


def draft_problem_led_email(record: Record) -> Record:
    """Draft a problem-led cold email for companies with deep research and prototype.

    Leads with observed problem, offers prototype as proof.
    """
    company = clean_text(record.get("company"))
    contact_name = _recipient(record)

    deep_research = record.get("deep_problem_research", {})
    problem_hypothesis = clean_text(deep_research.get("problem_hypothesis"))
    observed_signals = deep_research.get("observed_signals") or []

    prompt_gen = record.get("prompt_generation", {})
    artifact = clean_text(prompt_gen.get("artifact_path") or "")

    if not problem_hypothesis or not observed_signals:
        return {
            "email_body": "",
            "linkedin_note": "",
            "linkedin_message": "",
            "send_status": "blocked_insufficient_evidence",
            "draft_source": "problem_led",
        }

    # Build problem statement from first signal, truncated by word count (not
    # characters) so the final body can be steered into validate_outreach's
    # required 80-110 word range regardless of how long the real quote is.
    signal_words = _words(clean_text(observed_signals[0].get("text", "")))

    intro = f"Hi {contact_name}, I've been researching {company} and found a concrete operational gap worth flagging:"
    ask = (
        "I put together a small working prototype instead of just describing the idea, "
        "since a runnable demo says more than a pitch. I'm looking for a six-month onsite "
        "generalist internship in Bengaluru starting November 2026, where I can pick up "
        "real cross-functional work like this. Would it be useful to walk through the "
        "prototype together sometime this week?"
    )
    fixed_word_count = len(_words(intro)) + len(_words(ask))

    quote_budget = max(6, min(len(signal_words), 108 - fixed_word_count))
    signal_quote = " ".join(signal_words[:quote_budget])
    if len(signal_words) > quote_budget:
        signal_quote += "..."

    body = f"{intro} {signal_quote}. {ask}"

    # If the real quote was short, the body can still land under 80 words;
    # top up with a grounded, non-invented closing line rather than padding
    # with filler that would trip the humanizer's own rules.
    padding = " I focused on what's publicly visible rather than guessing at internals."
    if len(_words(body)) < 80:
        body = f"{body}{padding}"

    # LinkedIn connection note
    linkedin_note = (
        f"Hi {contact_name} - I found a specific problem in {company}'s operations "
        f"and built a prototype. Seeking an onsite internship from November 2026. Worth exploring?"
    )[:300]

    # LinkedIn message (after connection accepted)
    linkedin_message = (
        f"Thanks for connecting. I mapped the operational gap I found at {company} "
        f"and built a small prototype to explore it. Happy to walk through it if you're interested."
    )

    return {
        "email_body": body,
        "email_subject": f"{company.lower()} prototype idea",
        "linkedin_note": linkedin_note,
        "linkedin_message": linkedin_message,
        "send_status": "draft_needs_human_review",
        "draft_source": "problem_led",
        "artifact_path": artifact,
    }


def draft_outreach(record: Record) -> Record:
    """Draft outreach for an opportunity record (generic version).

    Returns dict with email_body, email_subject, linkedin_note, linkedin_message, send_status.
    Also supports legacy "followups" for backwards compatibility with testing.
    """
    # Check if this is a problem-led company (with deep research)
    if _is_problem_led_company(record):
        return draft_problem_led_email(record)

    # Generic internship listing outreach
    company = clean_text(record.get("company"))
    title = clean_text(record.get("title"))
    location = clean_text(record.get("location")) or "Bengaluru"
    contact_name = _recipient(record)
    research = record.get("research", {})
    solution = clean_text(research.get("solution_concept"))
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

    # LinkedIn connection note (under 300 chars)
    linkedin_note = (
        f"Hi {contact_name} - the {title} work at {company} caught my attention. "
        "I mapped the public context into a short evidence brief and one small "
        "idea. I'm seeking a six-month Bengaluru generalist internship from "
        "November 2026. Useful if I share it?"
    )
    if len(linkedin_note) > 300:
        linkedin_note = (
            f"Hi {contact_name} - the {title} work at {company} caught my "
            "attention. I mapped the public context into a short brief and one "
            "idea. Seeking a six-month Bengaluru internship from November 2026. "
            "Share it?"
        )[:300]

    # LinkedIn message (after connection accepted)
    linkedin_message = (
        f"Thanks for connecting. I mapped some of the context around the {title} role "
        f"and found an interesting angle. Happy to share if you'd like to see it."
    )

    # Legacy followups for backwards compatibility
    followups = _followups(record, company)

    if not solution:
        return {
            "email_subject": "founder office idea",
            "email_body": "",
            "linkedin_note": linkedin_note,
            "linkedin_message": linkedin_message,
            "followups": followups,
            "send_status": "blocked_insufficient_evidence",
            "artifact_mention_allowed": False,
            "strategy_id": strategy_id,
            "draft_source": "generic_opportunity",
        }

    return {
        "email_subject": "founder office idea",
        "email_body": body,
        "linkedin_note": linkedin_note,
        "linkedin_message": linkedin_message,
        "followups": followups,
        "send_status": "draft_needs_human_review",
        "artifact_mention_allowed": bool(artifact),
        "strategy_id": strategy_id,
        "draft_source": "generic_opportunity",
    }


def validate_outreach(draft: Record) -> list[str]:
    """Validate outreach drafts against humanizer rules.

    Hard-fail checks prevent marketing-speak, AI tone, and poor quality.
    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    # Skip validation for blocked drafts
    if draft.get("send_status") == "blocked_insufficient_evidence":
        return errors

    # Extract text fields (keep original for structure detection, clean version for text)
    subject_raw = draft.get("email_subject") or draft.get("subject", "")
    body_raw = draft.get("email_body", "")
    linkedin_note_raw = draft.get("linkedin_note", "")
    linkedin_message_raw = draft.get("linkedin_message", "")

    subject = clean_text(subject_raw)
    body = clean_text(body_raw)
    linkedin_note = clean_text(linkedin_note_raw)
    linkedin_message = clean_text(linkedin_message_raw)

    # Combine all text for some checks
    all_text = f"{subject} {body} {linkedin_note} {linkedin_message}".casefold()

    # For structural checks, use the raw body with newlines preserved
    body_with_structure = f"{subject_raw}\n{body_raw}"

    # 1. Check for forbidden punctuation (em dashes, curly quotes, emoji)
    for char, name in FORBIDDEN_PUNCTUATION.items():
        if char in all_text:
            errors.append(f"punctuation:{name}")

    if any(ord(c) > 127 for c in all_text if c in "😀😁😂😃😄😅😆😇😈😉😊😋😌😍"):
        errors.append("punctuation:emoji")

    # 2. Check for forbidden words
    for word in FORBIDDEN_WORDS:
        if f" {word} " in f" {all_text} ":  # Word boundaries
            errors.append(f"forbidden_word:{word}")

    # 3. Check for forbidden phrases
    for phrase in FORBIDDEN_PHRASES:
        if phrase in all_text:
            errors.append(f"forbidden_phrase:{phrase}")

    # 4. Check for -ing significance tails (highlighting, underscoring, reflecting)
    ing_tails = re.findall(r"(highlighting|underscoring|reflecting|showcasing|underlining|demonstrating)\b", all_text)
    if ing_tails:
        errors.append(f"ing_significance_tail:{ing_tails[0]}")

    # 5. Check for "not just X but Y" pattern
    if re.search(r"not just .+? but", all_text):
        errors.append("not_just_but_pattern")

    # 6. Check for three-item lists (check on raw text to preserve structure)
    list_items = re.findall(r"(?:^|\n)\s*(?:\d+\.|-|\*|•)\s+\S", f"\n{body_with_structure}", re.MULTILINE)
    if len(list_items) >= 3:
        errors.append(f"three_item_list:{len(list_items)}")

    # 7. Check for inline headers with bullets
    if re.search(r"\n\s*(•|-|\*)\s+\w+:", all_text):
        errors.append("inline_header_bullets")

    # Email-specific checks
    if body:
        word_count = len(_words(body))
        if not 80 <= word_count <= 110:
            errors.append(f"email_word_count:{word_count}")

        # Subject format
        if not 2 <= len(_words(subject)) <= 4 or subject != subject.casefold():
            errors.append("subject_format")

        # URL count
        url_count = len(re.findall(r"https?://", body))
        if url_count > 1:
            errors.append("too_many_urls")

    # LinkedIn-specific checks
    if linkedin_note:
        if len(linkedin_note) > 300:
            errors.append(f"linkedin_note_too_long:{len(linkedin_note)}")

    # Check send status validity
    if draft.get("send_status") not in {"draft_needs_human_review", "approved_manual_send", "blocked_insufficient_evidence"}:
        errors.append("invalid_send_status")

    return errors

