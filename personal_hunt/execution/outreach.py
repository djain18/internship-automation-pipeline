from __future__ import annotations

import re

from build_prompt import load_prompt_template
from models import Record, clean_text
from research import TEMPLATE_INFERENCE, TEMPLATE_SOLUTION

# Shared with watchlist_prompts.py's one-shot deep-dive prompts, so the copy
# rules Claude Code is told to follow are defined once, not retyped per
# feature and left to drift.
#
# 2026-09-14: rewritten from sourced cold email data (Daksh asked for the
# highest-converting principles inside the prompt). Sources, checked
# 2026-09-14, are listed with each rule in REVIEW.md; recheck them yearly.
EMAIL_COPY_RULES = (
    "- Body: 50-100 words, aim for about 75. Short enough to read on a phone "
    "without scrolling. (Instantly 2026 benchmark: best campaigns under 80 words; "
    "Gong 2026: replies drop sharply past 100.)",
    "- Any instructions in the listing win over every rule here: a required "
    "subject line, a named inbox, \"send your CV\", \"DM me\", a form. Follow them "
    "exactly and say in the output which one you followed.",
    "- First sentence is about them: the observation above, in their own words where "
    "possible. Never open with Daksh's name, college, or \"I came across\".",
    "- The observation has to lead to the ask. If you can delete the first line and "
    "the email still makes sense, the personalization is not doing its job.",
    "- Then one line on why Daksh fits, using exactly one verified fact from the "
    "section about him, the one closest to this role. No metrics, no adjectives about himself.",
    "- Be honest about the ask: a Founder's Office or generalist internship, "
    "Nov 2026 to Apr 2027, Bengaluru.",
    "- End with one low-effort interest question they can answer in a line "
    "(\"Would a short note on how I'd approach X be useful?\"), not a request for a "
    "30-minute call. (Gong Labs, 304,174 emails: asking for interest beat asking "
    "for a meeting in cold outreach.) One or two questions in total.",
    "- Write at a school reading level: short sentences, plain words. (Boomerang, "
    "40M emails, 2016: 3rd-grade emails got 53% responses vs 39% at college level.)",
    "- Slightly warm and a little opinionated. Neither neutral nor gushing.",
    "- Count sentences about them against sentences about Daksh. Theirs should win.",
    "- Subject: 2-4 lowercase words that look like an internal note "
    "(\"founder office intern\"). No clickbait, emoji, numbers, fake Re:/Fwd:, or their "
    "first name. Use the listing's subject line instead when it names one.",
    "- Plain text, at most one link, no images or signature banners. Attach "
    "{resume_basename}.pdf.",
    "- Also write a day-3 follow-up (under 60 words) that adds one new, sourced "
    "observation or a small useful idea; never \"just checking in\". (Instantly 2026: "
    "42% of replies came after the first email.)",
    "- LinkedIn note: 250-300 characters where possible.",
)

# The /humanizer skill's patterns, written into the prompt so they shape the
# first draft instead of only a clean-up pass.
HUMANIZER_RULES = (
    "- Use zero em dashes and no curly quotes. Use commas, full stops or brackets.",
    "- No AI vocabulary: delve, leverage, robust, testament, underscore, showcase, "
    "landscape, pivotal, crucial, vibrant, additionally, enhance, foster, garner, "
    "highlight (verb), intricate, key (adjective), valuable, align with.",
    "- No inflated significance (\"a pivotal moment\", \"reshaping\", \"at the "
    "intersection of\") and no promotional words (\"groundbreaking\", \"exciting "
    "opportunity\", \"passionate\").",
    "- No -ing tails that fake depth (\"..., highlighting their commitment to X\").",
    "- Say \"is\" and \"has\", not \"serves as\", \"stands as\" or \"boasts\".",
    "- No \"not just X, it's Y\", no rule of three, no synonym cycling, no false "
    "\"from X to Y\" ranges.",
    "- No chatbot or template phrases: \"I hope this email finds you well\", "
    "\"I came across\", \"let me know\", \"I hope this helps\", \"looking forward to\", "
    "\"just checking in\", \"synergy\", \"world-class\", \"cutting-edge\".",
    "- No flattery (\"your amazing work\"), no vague authorities (\"experts say\"), "
    "no filler (\"in order to\"), no stacked hedges.",
    "- No bold text, bullet lists, headings or emoji in the email.",
    "- Give it a pulse: mix short and longer sentences, use \"I\" naturally, and "
    "include one specific reaction to their post. Do not polish it into a template.",
)

# Verified in context/candidate-profile.md (2026-09-08). The resume metrics
# there stay out until Daksh confirms their evidence.
CANDIDATE_FACTS = (
    "- BCA student at Christ University, Bengaluru (June 2024 to May 2027). "
    "Available for an internship from about 1 Nov 2026 to 30 Apr 2027.",
    "- Godel Earth, Founder's Office: AI tooling on Amazon Bedrock, tool "
    "evaluation, LinkedIn and email automation.",
    "- ClapNow, Founder's Office: growth, influencer onboarding, seller operations.",
    "- Ravure, D2C operations: orders, inventory, COD, RTO, Shopify workflows.",
    "- Stratezic: GTM and lead-generation automation. Fire In The Belly: "
    "Founder's Office opportunity automation.",
    "- Built Rise, an internship discovery platform, and a job tracker with a "
    "Google Sheets backend for Fleetooo.",
    "- Works around an electrical retail shop: wholesalers, distributors, "
    "assortment and customers building homes.",
    "- Never cite a percentage, lead count, accuracy or time-saved figure for "
    "Daksh; none is verified.",
)

EMAIL_OUTPUT_FORMAT = (
    "After the tells from step 2, end with exactly this:",
    "",
    "Subject: ...",
    "Body: ...",
    "Attachment: ...",
    "Listing instruction followed: ... (or none)",
    "Word count: N | sentences about them / about Daksh: N / N",
    "Day-3 follow-up: ...",
    "LinkedIn note: ...",
)

EMAIL_AUDIT_STEPS = (
    "1. Write the draft following every rule above.",
    "2. Ask yourself: What makes this obviously AI-written? List the remaining tells "
    "in a few words.",
    "3. Rewrite to remove them, then check word count, zero em dashes, and that every "
    "fact appears in this prompt or a source you opened.",
    "4. Run the result through the /humanizer skill as a last pass. I will send it "
    "manually.",
)


def _email_rule_values(record: Record) -> dict[str, str]:
    """Placeholder values shared by both email prompts."""
    resume = clean_text(record.get("resume")) or "Daksh-Jain-Master"
    return {
        "resume_basename": resume,
        "candidate_facts": "\n".join(CANDIDATE_FACTS),
        "copy_rules": "\n".join(EMAIL_COPY_RULES).replace("{resume_basename}", resume),
        "humanizer_rules": "\n".join(HUMANIZER_RULES),
        "output_format": "\n".join(EMAIL_OUTPUT_FORMAT),
        "audit_steps": "\n".join(EMAIL_AUDIT_STEPS),
        "forbidden_words": ", ".join(FORBIDDEN_WORDS),
        "forbidden_phrases": "; ".join(f'"{phrase}"' for phrase in FORBIDDEN_PHRASES),
    }

_EMAIL_PROMPT_FALLBACK = """# {company_name}: draft the outreach email

## Verified facts

- Company: {company_name}
- Role: {role_title}
- Location: {location}
- Contact: {contact_line}
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

## About Daksh (verified; use one fact, the most relevant)

{candidate_facts}

## Draft the email

Write a cold email from Daksh to {recipient} built on the observation above.
Treat the inference and solution idea as Daksh's guesses: offer them as questions
or ideas, never as facts about the company. Never invent a metric, a familiarity,
or an artifact that does not exist.

### What gets cold emails answered

{copy_rules}

### Humanizer rules (apply while writing, not only after)

{humanizer_rules}

## Before you finish

{audit_steps}

{output_format}
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


def _contact_line(record: Record) -> str:
    """The contact as a verified fact: name / email (provenance), or an explicit
    "none found". Shared by both prompts. The email prompt used to print the
    Hi-there greeting fallback here, giving "Contact: there" (2026-09-14)."""
    contact = record.get("selected_contact") if isinstance(record.get("selected_contact"), dict) else {}
    bits = [clean_text(contact.get("name")), clean_text(contact.get("email"))]
    line = " / ".join(bit for bit in bits if bit)
    if not line:
        return "none found yet -- find the founder or hiring lead's public channel, with its source"
    details = [clean_text(contact.get("role"))]
    if contact.get("email") and contact.get("source_url"):
        details.append(f"published at {clean_text(contact.get('source_url'))}")
    details = [detail for detail in details if detail]
    return f"{line} ({'; '.join(details)})" if details else line


def _prompt_recipient(record: Record) -> str:
    """Who the drafted email is addressed to, in words Claude Code can act on."""
    contact = record.get("selected_contact") if isinstance(record.get("selected_contact"), dict) else {}
    name = _recipient(record)
    if name != "there":
        return name
    team = f"the {clean_text(record.get('company')) or 'company'} hiring team"
    email = clean_text(contact.get("email"))
    return f"{team} ({email})" if email else team


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
        # The quote may come from the job page behind the link, not the post.
        source_url = clean_text(research.get("observation_url")) or clean_text(record.get("source_url"))
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

    def researched(key: str, template: str) -> str:
        value = clean_text(research.get(key))
        return "" if value == clean_text(template) else value

    # Each section reads its own field. The inference slot used to fall back to
    # solution_concept, printing one sentence twice on every card (2026-09-14);
    # template sentences identical on every record count as no research.
    inference = clean_text(deep_research.get("problem_hypothesis")) or researched(
        "inference", TEMPLATE_INFERENCE
    )
    uncertainty = clean_text(research.get("uncertainty")) or (
        "Not yet validated -- this is inference from public information, not confirmed internally."
    )
    solution_concept = researched("solution_concept", TEMPLATE_SOLUTION)

    template = load_prompt_template("email_prompt.txt", _EMAIL_PROMPT_FALLBACK)
    return with_listing_context(record, _fill(
        template,
        _EMAIL_PROMPT_FALLBACK,
        company_name=clean_text(record.get("company")) or "the company",
        role_title=clean_text(record.get("title")) or "internship opportunity",
        location=clean_text(record.get("location")) or "Bengaluru",
        contact_line=_contact_line(record),
        recipient=_prompt_recipient(record),
        apply_url=clean_text(record.get("apply_url") or record.get("source_url") or record.get("company_url")),
        observed_signal=observed_signal,
        inference=inference or "None drawn -- observation alone was not enough to infer a specific problem.",
        uncertainty=uncertainty,
        solution_concept=solution_concept or "None yet -- draft one grounded in the observation above.",
        **_email_rule_values(record),
    ))


_RESEARCH_FIRST_PROMPT_FALLBACK = """# {company_name}: research first, then draft the outreach email

The listing did not describe the work in a sentence I could quote, so there is
no observed problem to build an email on yet. Do the research before writing.

## Verified facts (do not re-derive; do not contradict without new evidence)

- Company: {company_name}
- Role: {role_title}
- Location: {location}
- Listing: {source_url}
- Apply link: {apply_url}
- Contact: {contact_line}
- Resume to attach: {resume_basename}

## Step 1 - find one real, specific observation

Search {company_name}'s own website, careers page, founder posts, product
changelog and recent news. Find ONE thing that points at operational work this
intern would touch: a stated goal, a recent launch, a hiring push, a public
complaint, a process they describe. For it, give me:

- the exact quote, the URL it came from, and today's date;
- what you infer from it, labelled as inference, kept separate from the quote;
- what is still uncertain.

If you cannot find anything specific and sourced, stop and tell me. Do not draft
an email built on the job title alone.

## About Daksh (verified; use one fact, the most relevant)

{candidate_facts}

## Step 2 - draft the email

Only once Step 1 found a sourced observation. Write a cold email from Daksh to
the contact above, built on that observation. Keep your inference a question or
idea, never a stated fact about the company. Never invent a metric, a
familiarity, or an artifact that does not exist.

### What gets cold emails answered

{copy_rules}

### Humanizer rules (apply while writing, not only after)

{humanizer_rules}

## Before you finish

Show me the observation with its URL and today's date first. Then:

{audit_steps}

{output_format}
"""


def build_research_first_prompt(record: Record) -> str:
    """The prompt for a record whose listing never describes the work.

    build_email_prompt refuses those (correctly -- a prompt built on a job
    title invents its premise), and that refusal used to be the end of the
    road: all four approved matches on run_21ae706418041f9a, including
    SuprSend's and Kplor's Founder's Office internships, reached Daksh with no
    prompt at all. The per-record research the pipeline cannot afford (the
    Firecrawl free plan is already spent on funded companies) is exactly what
    Daksh's own Claude Code session can do, so this hands it the verified facts
    and makes a sourced observation the precondition for any draft.
    """
    contact_line = _contact_line(record)
    template = load_prompt_template("research_first_prompt.txt", _RESEARCH_FIRST_PROMPT_FALLBACK)
    return with_listing_context(record, _fill(
        template,
        _RESEARCH_FIRST_PROMPT_FALLBACK,
        company_name=clean_text(record.get("company")) or "the company",
        role_title=clean_text(record.get("title")) or "internship opportunity",
        location=clean_text(record.get("location")) or "Bengaluru",
        source_url=clean_text(record.get("source_url")) or "not recorded",
        apply_url=clean_text(record.get("apply_url") or record.get("source_url")) or "not recorded",
        contact_line=contact_line,
        **_email_rule_values(record),
    ))


# Phrases an employer uses to say applicants must not send AI-written
# messages. Ressl AI's live GTM Intern page (2026-09-13): "I can not emphasise
# enough how negatively we view usage of AI in any kind of comms content ...
# do not use AI to write it".
NO_AI_PHRASES = (
    "do not use ai", "don't use ai", "dont use ai", "without using ai", "without ai",
    "not written by ai", "no ai-generated", "no ai generated", "not ai-generated",
    "usage of ai in any kind of comms", "negatively we view usage of ai",
    "no chatgpt", "don't use chatgpt", "do not use chatgpt",
)
LISTING_CONTEXT_CHARS = 3500


def asks_for_no_ai(record: Record) -> str:
    """The exact no-AI phrase the listing uses, or ""."""
    text = " ".join(
        str(record.get(key) or "") for key in ("description", "listing_page_text")
    ).replace("’", "'").casefold()
    return next((phrase for phrase in NO_AI_PHRASES if phrase in text), "")


def with_listing_context(record: Record, prompt: str) -> str:
    """Prepend the employer's no-AI request when there is one, and append the
    listing's own text so Claude Code works from what the employer actually
    wrote, not from one sentence the pipeline picked."""
    if not prompt:
        return prompt
    parts: list[str] = []
    phrase = asks_for_no_ai(record)
    if phrase:
        parts.append(
            "## Read first: this employer asked for no AI-written messages\n\n"
            f'The listing says "{phrase}". Do NOT draft the email. Help me with research '
            "notes only (what to mention, what to ask), and I will write the message "
            "myself in my own words.\n"
        )
    parts.append(prompt.rstrip())
    body = str(record.get("listing_page_text") or record.get("description") or "").strip()
    if body:
        url = clean_text(record.get("listing_page_url") or record.get("source_url")) or "not recorded"
        clipped = body[:LISTING_CONTEXT_CHARS]
        if len(body) > LISTING_CONTEXT_CHARS:
            clipped = clipped.rsplit("\n", 1)[0] + "\n[... listing continues at the URL above]"
        parts.append(
            f"## The listing, verbatim (source: {url})\n\n"
            "Quote only from this text or from sources you open yourself.\n\n"
            f"{clipped}"
        )
    return "\n\n".join(parts) + "\n"


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
    # "built a prototype" is only true once one exists. prompt_generation writes
    # a prompt for a prototype, not the prototype, so without a built artifact
    # the note says what is actually true.
    built = "built a prototype" if artifact else "sketched a small prototype idea"
    linkedin_note = _fit_note(
        f"Hi {contact_name} - I found a specific problem in {company}'s operations "
        f"and {built}. Seeking an onsite internship from November 2026. Worth exploring?"
    )

    # LinkedIn message (after connection accepted)
    linkedin_message = (
        f"Thanks for connecting. I mapped the operational gap I found at {company} "
        f"and {built} to explore it. Happy to walk through it if you're interested."
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

    # LinkedIn connection note (under 300 chars). It may only mention a brief
    # when there is evidence to write one from: the old note promised "a short
    # evidence brief and one small idea" on every record, including the ones
    # blocked for having no evidence -- an invented artifact.
    if solution:
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
        linkedin_message = (
            f"Thanks for connecting. I mapped some of the context around the {title} role "
            f"and found an interesting angle. Happy to share if you'd like to see it."
        )
    else:
        linkedin_note = _fit_note(
            f"Hi {contact_name} - I saw the {title} opening at {company}. I'm a "
            "Bengaluru BCA student with founder's office and ops experience, looking "
            "for a six-month internship from November 2026. Open to a quick chat?"
        )
        linkedin_message = (
            f"Thanks for connecting. I'd like to be considered for the {title} role - "
            "happy to share my resume and the founder's office work I've done."
        )

    # Legacy followups for backwards compatibility
    followups = _followups(record, company)

    claude_prompt = build_email_prompt(record) if solution else ""
    if not claude_prompt:
        return {
            "email_subject": "founder office idea",
            "claude_prompt": build_research_first_prompt(record),
            "linkedin_note": linkedin_note,
            "linkedin_message": linkedin_message,
            "followups": followups,
            "send_status": "research_first_needs_human_review",
            "artifact_mention_allowed": bool(artifact),
            "strategy_id": strategy_id,
            "draft_source": "generic_opportunity",
        }

    return {
        "email_subject": "founder office idea",
        "claude_prompt": claude_prompt,
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
        "research_first_needs_human_review",
    }:
        errors.append("invalid_send_status")

    return errors

