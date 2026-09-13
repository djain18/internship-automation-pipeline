from __future__ import annotations

import re

from build_prompt import load_prompt_template
from models import Record, clean_text

# Shared with watchlist_prompts.py's one-shot deep-dive prompts, so the copy
# rules Claude Code is told to follow are defined once, not retyped per
# feature and left to drift.
EMAIL_COPY_RULES = (
    "- Email body: 80-110 words.",
    "- Subject: 2-4 lowercase words, no clickbait, emoji, fake reply prefix, "
    "or the recipient's first name.",
    "- One primary link.",
    "- LinkedIn note: 250-300 characters where possible.",
    "- Write like a thoughtful peer, not a vendor.",
    "- Lead with their situation, not Daksh's biography.",
)

_EMAIL_PROMPT_FALLBACK = """# {company_name}: draft the outreach email

## Verified facts

- Company: {company_name}
- Role: {role_title}
- Location: {location}
- Contact: {contact_name} ({contact_role})
- Apply link: {apply_url}
- Resume to attach: {resume_basename}

## What I actually observed

{observed_signal}

## What I am inferring (kept separate from the observation above)

{inference}

## What is still uncertain

{uncertainty}

## Solution idea

{solution_concept}

## Draft the email

Write a cold email from Daksh to {contact_name} using the observation and
inference above. Copy rules:

{copy_rules}

Never use these words: {forbidden_words}.
Never use these phrases: {forbidden_phrases}.
Never invent a metric, a familiarity, or an artifact that does not exist.
Never state the inference as a fact, or promise an unmeasured outcome.

## Before you finish

Run the drafted email through the /humanizer skill so it does not read like
AI-generated text. Show me the final email; I will send it manually.
"""

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

# Emoji and pictographic symbol blocks. A literal list of sample emoji only
# catches the samples; these ranges cover the pictographs, dingbats and
# variation selectors that actually turn up in drafted copy.
EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),  # pictographs, emoticons, transport, symbols
    (0x2600, 0x27BF),    # misc symbols and dingbats
    (0x2B00, 0x2BFF),    # arrows and geometric shapes used as emoji
    (0xFE0F, 0xFE0F),    # variation selector-16
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
        # ASCII apostrophe: U+2019 is in FORBIDDEN_PUNCTUATION, and this body
        # is a draft Daksh sends.
        "body": f"I'll close the loop here. If the {company} idea is relevant, I'm happy to share an outline; otherwise, no action needed.",
    })
    return output


def _words(text: str) -> list[str]:
    return re.findall(r"\b[\w’'-]+\b", text)


def _fit_note(note: str, limit: int = 300) -> str:
    """Trim a connection note to `limit` at a sentence boundary.

    A hard `[:300]` slice satisfies the validator's length check while leaving
    the note ending mid-word ("...from Nov"), which is unsendable. Cut at the
    last complete sentence instead, and only fall back to a word boundary when
    there isn't one.
    """
    if len(note) <= limit:
        return note
    cut = note[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end > 0:
        return cut[: end + 1]
    return cut[: cut.rfind(" ")].rstrip(" ,;:-") + "."


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


def _observed_signal_for_prompt(record: Record) -> tuple[str, bool]:
    """(text, has_real_signal) -- the one thing build_email_prompt refuses to
    proceed without. A prompt built on nothing real is worse than no prompt:
    it hands Claude Code a blank canvas to invent facts on, which is exactly
    what this pipeline exists to prevent."""
    deep_research = record.get("deep_problem_research") if isinstance(record.get("deep_problem_research"), dict) else {}
    signals = deep_research.get("observed_signals") or []
    if signals and isinstance(signals[0], dict) and signals[0].get("text"):
        text = clean_text(signals[0]["text"])
        url = clean_text(signals[0].get("url"))
        return (_quote_with_source(text, url), True)
    research = record.get("research") if isinstance(record.get("research"), dict) else {}
    # observed_problem_signal first: the LLM research path (research.py's
    # cached_bedrock_json merge) can overwrite solution_concept without ever
    # touching primary_responsibility, so checking only the latter would
    # return no signal on a real, LLM-researched record that draft_outreach's
    # own gate had already accepted. primary_responsibility is the fallback
    # for a record built without going through deterministic_research/LLM
    # research at all (e.g. a hand-built record from an older source).
    signal = clean_text(research.get("observed_problem_signal")) or clean_text(
        research.get("primary_responsibility")
    )
    if signal:
        source_url = clean_text(record.get("source_url"))
        return (_quote_with_source(signal, source_url), True)
    return ("", False)


def _quote_with_source(text: str, url: str) -> str:
    """Wrap in quotes for the prompt, unless the text already carries its
    own (e.g. 'The listing states: "..."'), which would otherwise nest
    quotes and read as broken -- exactly the AI-slop look this exists to
    avoid."""
    wrapped = text if '"' in text else f'"{text}"'
    return f"{wrapped} (source: {url})" if url else wrapped


def _fill(template: str, fallback: str, **values: str) -> str:
    """str.format the disk template, falling back to the embedded one when it
    cannot be filled. templates/email_prompt.txt is hand-editable, and one
    stray brace or renamed placeholder in it raises KeyError/ValueError out of
    draft_outreach, which run_pipeline calls in an unguarded loop -- a typo in
    a text file would take down the whole run. load_prompt_template already
    promises a missing file degrades instead of crashing; a malformed one is
    the same failure mode."""
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return fallback.format(**values)


def build_email_prompt(record: Record) -> str:
    """A self-contained, paste-ready Claude Code prompt in place of a
    pre-written email body. Kimi never wrote outreach copy -- draft_outreach
    and draft_problem_led_email were hardcoded Python f-strings that just
    swapped the company name in, which read as mail-merge slop. Daksh drafts
    every email himself in Claude Code with /humanizer instead; this hands
    that conversation everything it needs with no other file access."""
    observed_signal, has_signal = _observed_signal_for_prompt(record)
    if not has_signal:
        return ""

    deep_research = record.get("deep_problem_research") if isinstance(record.get("deep_problem_research"), dict) else {}
    research = record.get("research") if isinstance(record.get("research"), dict) else {}
    contact = record.get("selected_contact") if isinstance(record.get("selected_contact"), dict) else {}

    inference = clean_text(deep_research.get("problem_hypothesis")) or clean_text(research.get("solution_concept"))
    uncertainty = clean_text(research.get("uncertainty")) or (
        "Not yet validated -- this is inference from public information, not confirmed internally."
    )
    solution_concept = clean_text(research.get("solution_concept")) or inference

    template = load_prompt_template("email_prompt.txt", _EMAIL_PROMPT_FALLBACK)
    return _fill(
        template,
        _EMAIL_PROMPT_FALLBACK,
        company_name=clean_text(record.get("company")) or "the company",
        role_title=clean_text(record.get("title")) or "internship opportunity",
        location=clean_text(record.get("location")) or "Bengaluru",
        contact_name=contact.get("name") or "there",
        contact_role=clean_text(contact.get("role")) or "hiring contact",
        apply_url=clean_text(record.get("apply_url") or record.get("source_url") or record.get("company_url")),
        resume_basename=clean_text(record.get("resume")) or "Daksh-Jain-Master",
        observed_signal=observed_signal,
        inference=inference or "None drawn -- observation alone was not enough to infer a specific problem.",
        uncertainty=uncertainty,
        solution_concept=solution_concept or "None yet -- draft one grounded in the observation above.",
        copy_rules="\n".join(EMAIL_COPY_RULES),
        forbidden_words=", ".join(FORBIDDEN_WORDS),
        forbidden_phrases="; ".join(f'"{phrase}"' for phrase in FORBIDDEN_PHRASES),
    )


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
            "claude_prompt": "",
            "linkedin_note": "",
            "linkedin_message": "",
            "send_status": "blocked_insufficient_evidence",
            "draft_source": "problem_led",
        }

    # LinkedIn connection note -- still hand-drafted here, unlike the email.
    # It is short and structurally simple (name, one observation, one ask),
    # which is exactly where a template reads fine; the email is where the
    # mail-merge sameness actually showed.
    linkedin_note = _fit_note(
        f"Hi {contact_name} - I found a specific problem in {company}'s operations "
        f"and built a prototype. Seeking an onsite internship from November 2026. Worth exploring?"
    )

    # LinkedIn message (after connection accepted)
    linkedin_message = (
        f"Thanks for connecting. I mapped the operational gap I found at {company} "
        f"and built a small prototype to explore it. Happy to walk through it if you're interested."
    )

    claude_prompt = build_email_prompt(record)
    return {
        "claude_prompt": claude_prompt,
        "email_subject": f"{company.lower()} prototype idea",
        "linkedin_note": linkedin_note,
        "linkedin_message": linkedin_message,
        # A prompt built on nothing real hands Claude Code a blank canvas to
        # invent facts on -- if build_email_prompt refused, this draft is
        # blocked too, not silently "ready for review" with an empty prompt.
        "send_status": "draft_needs_human_review" if claude_prompt else "blocked_no_evidence",
        "draft_source": "problem_led",
        "artifact_path": artifact,
    }


def draft_outreach(record: Record) -> Record:
    """Draft outreach for an opportunity record (generic version).

    Returns dict with claude_prompt, email_subject, linkedin_note, linkedin_message,
    send_status. Also supports legacy "followups" for backwards compatibility with testing.
    """
    # Check if this is a problem-led company (with deep research)
    if _is_problem_led_company(record):
        return draft_problem_led_email(record)

    # Generic internship listing outreach
    company = clean_text(record.get("company"))
    title = clean_text(record.get("title"))
    contact_name = _recipient(record)
    research = record.get("research", {})
    solution = clean_text(research.get("solution_concept"))
    strategy_id = choose_strategy(record)
    artifact = _approved_artifact(record)

    # LinkedIn connection note (under 300 chars)
    linkedin_note = (
        f"Hi {contact_name} - the {title} work at {company} caught my attention. "
        "I mapped the public context into a short evidence brief and one small "
        "idea. I'm seeking a six-month Bengaluru generalist internship from "
        "November 2026. Useful if I share it?"
    )
    if len(linkedin_note) > 300:
        linkedin_note = _fit_note(
            f"Hi {contact_name} - the {title} work at {company} caught my "
            "attention. I mapped the public context into a short brief and one "
            "idea. Seeking a six-month Bengaluru internship from November 2026. "
            "Share it?"
        )

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
            "claude_prompt": "",
            "linkedin_note": linkedin_note,
            "linkedin_message": linkedin_message,
            "followups": followups,
            "send_status": "blocked_insufficient_evidence",
            "artifact_mention_allowed": False,
            "strategy_id": strategy_id,
            "draft_source": "generic_opportunity",
        }

    claude_prompt = build_email_prompt(record)
    return {
        "email_subject": "founder office idea",
        "claude_prompt": claude_prompt,
        "linkedin_note": linkedin_note,
        "linkedin_message": linkedin_message,
        "followups": followups,
        "send_status": "draft_needs_human_review" if claude_prompt else "blocked_no_evidence",
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

    # Extract text fields (keep original for structure detection, clean version for text).
    # There is no email_body any more -- outreach.py no longer drafts the
    # email itself (see build_email_prompt); subject_raw stays only as a
    # short label, not the real subject Daksh will send.
    subject_raw = draft.get("email_subject") or draft.get("subject", "")
    linkedin_note_raw = draft.get("linkedin_note", "")
    linkedin_message_raw = draft.get("linkedin_message", "")

    subject = clean_text(subject_raw)
    linkedin_note = clean_text(linkedin_note_raw)
    linkedin_message = clean_text(linkedin_message_raw)

    # Combine all text for some checks
    all_text = f"{subject} {linkedin_note} {linkedin_message}".casefold()
    prose = all_text

    # For structural checks, use the raw text with newlines preserved. The
    # LinkedIn note and message are the only prose left that Daksh actually
    # sends from this pipeline; pointing these at subject_raw (a 2-4 word
    # subject that can never hold a bulleted list) left checks 6 and 7 dead
    # -- they could not fire on any draft this module produces.
    body_with_structure = f"{linkedin_note_raw}\n{linkedin_message_raw}"

    # 1. Check for forbidden punctuation (em dashes, curly quotes, emoji)
    for char, name in FORBIDDEN_PUNCTUATION.items():
        if char in all_text:
            errors.append(f"punctuation:{name}")

    # Emoji by codepoint range, not by a hand-listed sample: the earlier
    # 14-emoji literal let every other emoji (rocket, sparkles, check mark)
    # through untouched.
    if any(any(low <= ord(c) <= high for low, high in EMOJI_RANGES) for c in all_text):
        errors.append("punctuation:emoji")

    # 2. Check for forbidden words
    for word in FORBIDDEN_WORDS:
        if f" {word} " in f" {prose} ":  # Word boundaries
            errors.append(f"forbidden_word:{word}")

    # 3. Check for forbidden phrases
    for phrase in FORBIDDEN_PHRASES:
        if phrase in prose:
            errors.append(f"forbidden_phrase:{phrase}")

    # 4. Check for -ing significance tails (highlighting, underscoring, reflecting)
    ing_tails = re.findall(r"(highlighting|underscoring|reflecting|showcasing|underlining|demonstrating)\b", prose)
    if ing_tails:
        errors.append(f"ing_significance_tail:{ing_tails[0]}")

    # 5. Check for "not just X but Y" pattern
    if re.search(r"not just .+? but", prose):
        errors.append("not_just_but_pattern")

    # 6. Check for three-item lists (check on raw text to preserve structure)
    list_items = re.findall(r"(?:^|\n)\s*(?:\d+\.|-|\*|•)\s+\S", f"\n{body_with_structure}", re.MULTILINE)
    if len(list_items) >= 3:
        errors.append(f"three_item_list:{len(list_items)}")

    # 7. Check for inline headers with bullets. Must run on the raw body:
    # clean_text collapses every newline into a space, so this pattern could
    # never match all_text and the check was dead.
    if re.search(r"\n\s*(•|-|\*)\s+\w+:", body_with_structure):
        errors.append("inline_header_bullets")

    # No email_body checks: outreach.py no longer drafts the email itself
    # (see build_email_prompt) -- Daksh writes the real email in Claude Code,
    # outside this pipeline's reach, so word count and subject format are no
    # longer this validator's job.

    # LinkedIn-specific checks
    if linkedin_note:
        if len(linkedin_note) > 300:
            errors.append(f"linkedin_note_too_long:{len(linkedin_note)}")

    # Check send status validity
    if draft.get("send_status") not in {
        "draft_needs_human_review", "approved_manual_send",
        "blocked_insufficient_evidence", "blocked_no_evidence",
    }:
        errors.append("invalid_send_status")

    return errors

