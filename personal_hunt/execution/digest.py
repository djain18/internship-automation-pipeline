from __future__ import annotations

import base64
import html
import json
import os
from email.message import EmailMessage
from pathlib import Path

from models import Record


def _section(title: str, records: list[Record]) -> str:
    lines = [f"## {title}", ""]
    if not records:
        return "\n".join(lines + ["No qualifying records.", ""])
    for index, item in enumerate(records, 1):
        contact = item.get("selected_contact", {})
        lines.extend(
            [
                f"### {index}. {item['company']} - {item['title']}",
                "",
                f"- Score: {item.get('score')}/100",
                f"- Kimi fit: {item.get('llm_fit_score')}/100 (rank {item.get('llm_rank')})",
                f"- Kimi reason: {item.get('llm_rank_reason')}",
                f"- Lane: {item.get('lane')}",
                f"- Location: {item.get('location')} ({item.get('location_class')})",
                f"- Posted: {item.get('posted_date')} ({item.get('posted_date_basis')})",
                f"- Verification: {item.get('verification_status')} / {item.get('source_confidence')}",
                f"- Source: {item.get('source_url')}",
                f"- Contact: {contact.get('name') or contact.get('status', 'unknown')}",
                f"- Resume: {item.get('resume')}",
                f"- Evidence pack: {item.get('evidence_pack_path', 'not generated')}",
                "- Human action: open sources, verify inference, review draft",
                "",
            ]
        )
    return "\n".join(lines)


def _verification_section(records: list[Record]) -> str:
    """Unverified LinkedIn leads, kept apart from anything Kimi approved."""

    lines = ["## Needs your verification (unverified LinkedIn leads)", ""]
    if not records:
        return "\n".join(lines + ["No leads are waiting on manual verification.", ""])
    lines.extend(
        [
            "These cleared every other filter but carry a LinkedIn or lnkd.in link "
            "that this pipeline is not permitted to open. They are machine-collected "
            "unverified leads, they are NOT approved matches, and they do not count "
            "toward the daily target.",
            "",
        ]
    )
    for index, item in enumerate(records, 1):
        lines.extend(
            [
                f"### {index}. {item.get('company')} - {item.get('title')}",
                "",
                f"- Location: {item.get('location')} ({item.get('location_class')})",
                f"- Posted: {item.get('posted_date')} ({item.get('posted_date_basis')})",
                f"- Source: {item.get('source_url')}",
                f"- Apply link: {item.get('apply_url')}",
                "- Human action: open the link yourself, confirm the role is real "
                "and still open, then decide",
                "",
            ]
        )
    return "\n".join(lines)


def _funding_section(title: str, records: list[Record]) -> str:
    lines = [f"## {title}", ""]
    if not records:
        return "\n".join(lines + ["No qualifying new funding events found.", ""])
    for index, item in enumerate(records, 1):
        detail = item.get("source_reported_detail") or item.get("headline")
        lines.extend(
            [
                f"### {index}. {item.get('company')}",
                "",
                f"- Event date: {item.get('event_date')} ({item.get('funding_window')})",
                f"- Source report: {item.get('headline')}",
                f"- Source: {item.get('source_url')}",
                f"- Verification: {item.get('verification_status')} / {item.get('source_confidence')}",
                f"- Source detail: {detail}",
                "- Human action: open the source and confirm amount, round, investors, location, and size",
                "",
            ]
        )
    return "\n".join(lines)


def _problem_section(records: list[Record]) -> str:
    """Legacy section for funding-event problem hypotheses (Phase 1-6)."""
    lines = ["## Evidence-backed problem hypotheses", ""]
    shown = 0
    for item in records:
        research = item.get("problem_research") or {}
        hypothesis = research.get("problem_hypothesis")
        if not hypothesis or research.get("problem_status") != "inference_needs_validation":
            continue
        shown += 1
        lines.extend(
            [
                f"### {shown}. {item.get('company')}",
                "",
                f"- Inference needing validation: {hypothesis}",
                f"- Why now: {research.get('why_now')}",
                f"- Possible micro-solution: {research.get('solution_concept')}",
                f"- Evidence: {', '.join(research.get('problem_evidence_urls') or [])}",
                f"- Uncertainty: {research.get('uncertainty')}",
                "",
            ]
        )
    if not shown:
        lines.extend(
            [
                "No defensible company-problem hypothesis was found; funding facts were retained without invention.",
                "",
            ]
        )
    return "\n".join(lines)


def _watchlist_movement_section(discovered: list[Record]) -> str:
    """Summary of activity at each watchlist company.

    Watchlist companies are those with company_url_basis == "watchlist".
    This section provides a one-line status per watchlist company so Daksh
    can see at a glance what changed since yesterday.
    """
    watchlist_companies = [
        item for item in discovered
        if item.get("company_url_basis") == "watchlist"
    ]

    lines = ["## Watchlist movement", ""]

    if not watchlist_companies:
        lines.append("No watchlist companies present this run.")
        lines.append("")
        return "\n".join(lines)

    for item in watchlist_companies:
        company = item.get("company", "Unknown")
        deep_research = item.get("deep_problem_research") or {}

        # Build a one-line status based on what we found
        evidence_count = deep_research.get("evidence_count", 0)
        if evidence_count == 0:
            status = "no activity observed"
        else:
            status = f"{evidence_count} signal{'s' if evidence_count != 1 else ''} found"

        lines.append(f"- **{company}**: {status}")

    lines.append("")
    return "\n".join(lines)


def _problem_brief_block(company: Record) -> list[str]:
    """Render one problem brief company block for Phase 7 digest.

    Returns a list of lines (not joined) for a single company's full problem
    brief including observed signals, hypothesis, prompt, contact, and drafts.
    """
    lines: list[str] = []
    company_name = company.get("company", "Unknown")
    deep_research = company.get("deep_problem_research") or {}
    prompt_gen = company.get("prompt_generation") or {}
    contact = company.get("selected_contact") or {}
    outreach = company.get("outreach") or {}

    lines.append(f"### {company_name}")
    lines.append("")

    # Observed signals with evidence URLs
    lines.append("**Observed signals:**")
    lines.append("")
    signals = deep_research.get("observed_signals") or []
    if signals:
        for signal in signals:
            text = signal.get("text", "")
            url = signal.get("url", "")
            if text and url:
                lines.append(f"- \"{text}\" — {url}")
        lines.append("")
    else:
        lines.append("(No signals observed)")
        lines.append("")

    # Problem hypothesis, labeled as inference
    hypothesis = deep_research.get("problem_hypothesis", "")
    if hypothesis:
        lines.append("**Inference (not verified):**")
        lines.append("")
        lines.append(f"{hypothesis}")
        lines.append("")

    # Fenced Claude Code prompt
    prompt_text = prompt_gen.get("prompt_text", "")
    lines.append("**Claude Code prompt (paste-ready):**")
    lines.append("")
    if prompt_text:
        lines.append("```")
        lines.append(prompt_text)
        lines.append("```")
    else:
        # Handle insufficient evidence honestly
        basis = prompt_gen.get("prompt_basis", "unknown")
        status = outreach.get("send_status", "")
        validation_errors = prompt_gen.get("validation_errors") or []
        if prompt_gen.get("llm_status") == "blocked_validation" and validation_errors:
            lines.append(
                "*A prompt was generated but failed a quality check, so it is withheld:*"
            )
            for error in validation_errors:
                lines.append(f"- {error}")
        elif prompt_gen.get("llm_status") == "skipped_unsupported_hypothesis":
            lines.append(
                "*A real page or post was found, but it did not support an internal-problem "
                "hypothesis, so no prototype was generated. This is the pipeline correctly "
                "refusing to invent a problem from thin evidence, not a failure.*"
            )
        elif status == "blocked_insufficient_evidence" or basis == "insufficient_evidence":
            lines.append("*Insufficient evidence to generate a prompt. The observed signals may need more depth.*")
        else:
            lines.append("*Prompt generation was not completed for this company.*")
    lines.append("")

    # Contact information
    lines.append("**Contact:**")
    lines.append("")
    contact_name = contact.get("name", "")
    contact_email = contact.get("email", "")
    contact_linkedin = contact.get("linkedin", "")
    # choose_contact emits "source_url"/"access_date", never "source" -- reading
    # the wrong key silently dropped the provenance line CLAUDE.md requires on
    # every contact.
    contact_source = contact.get("source_url", "")
    contact_access_date = contact.get("access_date", "")
    contact_status = contact.get("status", "")

    if contact_name:
        lines.append(f"- Name: {contact_name}")
    if contact_email:
        lines.append(f"- Email: {contact_email}")
    if contact_linkedin:
        lines.append(f"- LinkedIn: {contact_linkedin}")
    if contact_source:
        lines.append(f"- Source: {contact_source}")
    if contact_access_date:
        lines.append(f"- Accessed: {contact_access_date}")
    if contact_status and not contact_name:
        lines.append(f"- Status: {contact_status}")
    lines.append("")

    # Three humanized drafts
    lines.append("**Outreach drafts:**")
    lines.append("")

    validation_errors = outreach.get("validation_errors", [])
    send_status = outreach.get("send_status", "")

    if send_status == "blocked_insufficient_evidence":
        lines.append("*Blocked: insufficient evidence for outreach. Research the company more before contacting.*")
    elif send_status == "blocked_validation":
        lines.append(f"*Blocked by humanizer rules: {'; '.join(validation_errors)}*")
    else:
        # Email draft
        email_body = outreach.get("email_body", "")
        if email_body:
            lines.append("**Email (cold outreach):**")
            lines.append("")
            lines.append(email_body)
            lines.append("")

        # LinkedIn note (connection request)
        linkedin_note = outreach.get("linkedin_note", "")
        if linkedin_note:
            lines.append("**LinkedIn connection note:**")
            lines.append("")
            lines.append(linkedin_note)
            lines.append("")

        # LinkedIn message (after connection accepted)
        linkedin_message = outreach.get("linkedin_message", "")
        if linkedin_message:
            lines.append("**LinkedIn message (after connection):**")
            lines.append("")
            lines.append(linkedin_message)
            lines.append("")

    return lines


def _problem_briefs_section(discovered: list[Record]) -> str:
    """Full problem briefs for all researched (discovered) companies.

    Phase 7: The core section that gives Daksh everything needed to understand
    a company's problem and reach out with a working prototype. Includes observed
    signals with quoted evidence, hypothesis (labeled as inference), paste-ready
    Claude Code prompt, contact info, and three humanized drafts.
    """
    if not discovered:
        lines = ["## Problem briefs for researched companies", ""]
        lines.append("No companies were researched this run.")
        lines.append("")
        return "\n".join(lines)

    lines = ["## Problem briefs for researched companies", ""]

    for item in discovered:
        block_lines = _problem_brief_block(item)
        lines.extend(block_lines)

    return "\n".join(lines)


def _weekly_target_section(records: list[Record]) -> str:
    lines = ["## Weekly founder targets (separate from internship matches)", ""]
    if not records:
        return "\n".join(lines + ["No company cleared the two-signal target gate.", ""])
    for index, item in enumerate(records, 1):
        contact = item.get("selected_contact") or {}
        lines.extend(
            [
                f"### {index}. {item.get('company')}",
                "",
                f"- Lane: {item.get('lane')}",
                f"- Company: {item.get('company_url')}",
                f"- Contact: {contact.get('name') or contact.get('email') or contact.get('status', 'research required')}",
                f"- Contact priority: {contact.get('contact_priority', 'unknown')}",
                f"- Strategy: {(item.get('outreach') or {}).get('strategy_id', 'not drafted')}",
                "- Signals:",
                *[
                    f"  - {signal.get('date')}: {signal.get('observation')} — {signal.get('url')}"
                    for signal in item.get("signals", [])
                ],
                "- Human action: verify both signals and approve any artifact before sending manually",
                "",
            ]
        )
    return "\n".join(lines)


def _cost_section(run: Record) -> str:
    usage = run.get("llm_usage", {}) or {}
    cache = run.get("cache_statistics", {}) or {}
    lines = ["## Run cost and source yield", ""]
    lines.append(
        f"- LLM: {usage.get('calls', 0)} calls, {usage.get('cache_hits', 0)} cache hits, "
        f"{usage.get('total_tokens', 0)} tokens in {usage.get('elapsed_ms', 0)}ms. "
        "No dollar baseline is set before seven optimized runs."
    )
    lines.append(
        f"- Cache: {cache.get('entries', 0)} entries, {cache.get('hits', 0)} hits."
    )
    yields = run.get("source_yield", []) or []
    if yields:
        parts = [
            f"{item.get('source')}: raw {item.get('raw', 0)}/eligible {item.get('eligible', 0)}"
            f"/approved {item.get('kimi_approved', 0)}"
            for item in yields
        ]
        lines.append(f"- Yield: {'; '.join(parts)}.")
        zero_yield = [item for item in yields if item.get("unique") and not item.get("eligible")]
        if zero_yield:
            lines.append("- Sources that yielded nothing:")
            for item in zero_yield:
                reason = item.get("dominant_rejection_reason")
                count = item.get("dominant_rejection_count", 0)
                reason_text = f", mostly {reason} ({count})" if reason else ""
                lines.append(
                    f"  - {item.get('source')}: {item.get('unique', 0)} reviewed, 0 eligible{reason_text}."
                )
    else:
        lines.append("- Yield: no source activity recorded.")
    role_judgement = run.get("role_judgement", {}) or {}
    skipped = int(role_judgement.get("skipped_over_cap", 0) or 0)
    if skipped:
        lines.append(
            f"- Cross-functional judging hit its per-run cap: {skipped} candidate(s) "
            "skipped_over_cap without a Tier 2 read. Raise max_role_judgements_per_run "
            "in scoring.yml if this recurs."
        )
    extraction = next(
        (item for item in run.get("source_health", []) if item.get("source_id") == "linkedin_posts_apify_extraction"),
        None,
    )
    if extraction:
        lines.append(
            f"- LinkedIn field extraction: {extraction.get('resolved', extraction.get('record_count', 0))} "
            f"resolved of {extraction.get('attempted', 0)} attempted "
            f"(status {extraction.get('status')})."
        )
        extraction_skipped = int(extraction.get("skipped_over_cap", 0) or 0)
        if extraction_skipped:
            lines.append(
                f"- LinkedIn extraction hit its per-run cap: {extraction_skipped} qualifying "
                "post(s) skipped. Raise max_linkedin_extractions_per_run in scoring.yml "
                "if this recurs."
            )
    lines.append("")
    return "\n".join(lines)


def _spotted_section(records: list[Record]) -> str:
    lines = ["## Your spotted leads (open and decide)", ""]
    if not records:
        lines.extend(
            [
                "Nothing spotted. Drop LinkedIn post URLs (one per line) into "
                "personal_hunt/input/linkedin-leads.txt and they appear here.",
                "",
            ]
        )
        return "\n".join(lines)
    for index, item in enumerate(records, 1):
        lines.extend(
            [
                f"### {index}. {item.get('source_url')}",
                "",
                "- Human action: open the link yourself, confirm a real Bengaluru "
                "opening, then apply or add the company to the watchlist",
                "",
            ]
        )
    return "\n".join(lines)


def _glance_section(records: list[Record]) -> str:
    lines = ["## Worth a glance (unverified, machine cannot qualify these)", ""]
    if not records:
        lines.extend(
            [
                "No FO-shaped unverified posts today.",
                "",
            ]
        )
        return "\n".join(lines)
    for index, item in enumerate(records, 1):
        lines.extend(
            [
                f"### {index}. {item.get('source_url')}",
                "",
                f"- Says: {item.get('excerpt')}",
                "- Human action: 10-second look. If it names a real Bengaluru "
                "internship with an employer, apply directly or drop the company "
                "in the watchlist; otherwise ignore",
                "",
            ]
        )
    return "\n".join(lines)


def _worth_a_look_records(run: Record) -> list[Record]:
    """Records Kimi scored 60-69: below llm_fit_threshold (70), so never
    digest_approved and never counted toward the daily five, but close
    enough that Daksh asked to see them with Kimi's own reason rather than
    have them silently disappear."""
    all_selected = run.get("primary", []) + run.get("remote_fallback", [])
    return [
        item
        for item in all_selected
        if not item.get("digest_approved")
        and item.get("llm_relevant")
        and not item.get("llm_spam")
        and 60 <= int(item.get("llm_fit_score", 0)) <= 69
    ]


def _worth_a_look_section(run: Record) -> str:
    records = _worth_a_look_records(run)
    lines = [
        "## Worth a look (fit 60-69, not counted toward the daily five)",
        "",
        "Kimi scored these below the 70 admission bar but close enough that "
        "you may want to judge them yourself.",
        "",
    ]
    if not records:
        lines.extend(["None today.", ""])
        return "\n".join(lines)
    for index, item in enumerate(records, 1):
        lines.extend(
            [
                f"### {index}. {item.get('company')} - {item.get('title')} "
                f"(fit {item.get('llm_fit_score')})",
                "",
                f"- Apply: {item.get('apply_url') or item.get('source_url')}",
                f"- Kimi's reason: {item.get('llm_rank_reason')}",
                "",
            ]
        )
    return "\n".join(lines)


def _send_queue_section(run: Record) -> str:
    queue = run.get("send_queue", []) or []
    stale = run.get("stale_queue", []) or []
    streak = int(run.get("send_streak_days", 0) or 0)
    quota = int(run.get("daily_send_quota", 3) or 3)
    lines = ["## Today's send queue (manual sends win internships)", ""]
    lines.append(
        f"Send streak: {streak} day{'s' if streak != 1 else ''} with digest sends. "
        f"Today's quota: {quota}."
    )
    lines.append("")
    if not queue:
        lines.extend(["Queue is clear: every approved match was already emailed.", ""])
    for index, item in enumerate(queue, 1):
        lines.extend(
            [
                f"### {index}. {item.get('company')} - {item.get('title')}",
                "",
                f"- Score {item.get('score')}/100, waiting {item.get('age_days')}d, resume {item.get('resume')}",
                f"- Apply: {item.get('apply_url')}",
                f"- Contact: {item.get('contact') or 'research required'}",
                "- Human action: send the approved draft today, then log sent_at in the Sheet",
                "",
            ]
        )
    if stale:
        lines.append(f"Going stale (approved, unsent, {len(stale)}):")
        lines.append("")
        for item in stale:
            lines.append(
                f"- {item.get('company')} - {item.get('title')} "
                f"(waiting {item.get('age_days')}d): send or drop it today"
            )
        lines.append("")
    return "\n".join(lines)


def render_digest(run: Record) -> str:
    failed = [item for item in run.get("source_health", []) if item.get("status") != "ok"]
    failure_lines = (
        "\n".join(
            f"- {item['source_id']}: {item['status']} - "
            f"{item.get('human_action') or item.get('error_message') or 'inspect source'}"
            for item in failed
        )
        if failed
        else "- No source failures recorded."
    )
    primary = run.get("digest_primary", [])
    remote = run.get("digest_remote_fallback", [])
    all_selected = run.get("primary", []) + run.get("remote_fallback", [])
    withheld = [item for item in all_selected if not item.get("digest_approved")]
    target = int(run.get("daily_target", 10))
    minimum = int(run.get("daily_min_target", 5))
    admitted_count = len(primary) + len(remote)
    shadow = os.getenv("SHADOW_MODE", "true").casefold() in {"1", "true", "yes"}
    label = "SHADOW / HUMAN REVIEW" if shadow else "HUMAN REVIEW REQUIRED"
    stale_notice = run.get("staleness_warning", "")
    discovered = run.get("discovered_for_research", [])
    return "\n".join(
        [
            f"# Internship hunt digest - {run['run_date']}",
            "",
            f"**{label}**",
            *(["", f"**{stale_notice}**"] if stale_notice else []),
            "",
            (
                f"Internships: prior {run.get('internship_window_days', 10)} days. "
                f"Funding: primary {run.get('funding_primary_window_days', 15)} days; "
                f"labeled extension through {run.get('funding_extension_window_days', 30)} days."
            ),
            "",
            # Phase 7: Section 1 - Approved internship matches (unchanged)
            _section("New Bengaluru internships approved by Kimi", primary),
            _section("New India-remote internships approved by Kimi", remote),
            "## Kimi admission summary",
            "",
            (
                f"{admitted_count} admitted (daily target {minimum}-{target}); "
                f"{len(withheld)} withheld as low-fit, irrelevant, spam, or unscored. "
                "Withheld records remain in the audit trail."
            ),
            (
                "Quality target shortfall: fewer than five internships cleared every gate; "
                "the digest was not padded."
                if admitted_count < minimum
                else "Daily internship quality target met."
            ),
            "",
            _worth_a_look_section(run),
            # Phase 7: Section 2 - Watchlist movement summary (NEW)
            _watchlist_movement_section(discovered),
            # Phase 7: Section 3 - Problem briefs for all researched companies (NEW)
            _problem_briefs_section(discovered),
            # Phase 7: Section 4 - Verification, funding, health (existing sections)
            _verification_section(run.get("needs_verification", [])),
            _spotted_section(run.get("spotted_leads", [])),
            _glance_section(run.get("glance_queue", [])),
            _send_queue_section(run),
            _weekly_target_section(run.get("weekly_targets", [])),
            _funding_section("Newly funded startups (0-15 days)", run.get("funding_primary", [])),
            _funding_section(
                "Earlier this month (16-30 days; extension)",
                run.get("funding_extended", []),
            ),
            _problem_section(run.get("funding_primary", []) + run.get("funding_extended", [])),
            _cost_section(run),
            "## Source health",
            "",
            failure_lines,
            "",
            "## Reminder",
            "",
            "These are research leads, not verified offers. Open every source, validate "
            "company size and evidence, then send manually. Mailsuite opens are weak "
            "signals; replies are authoritative.",
            "",
        ]
    )


def _watchlist_movement_html(discovered: list[Record]) -> str:
    """HTML counterpart of _watchlist_movement_section -- the plain-text
    digest and the HTML digest must show the same content, since Gmail
    renders the HTML part when both are present and a section only added
    to render_digest would never reach the actual inbox."""
    watchlist_companies = [
        item for item in discovered if item.get("company_url_basis") == "watchlist"
    ]
    if not watchlist_companies:
        return ""
    items: list[str] = []
    for item in watchlist_companies:
        company = html.escape(str(item.get("company") or "Unknown"))
        deep_research = item.get("deep_problem_research") or {}
        evidence_count = deep_research.get("evidence_count", 0)
        status = (
            "no activity observed"
            if not evidence_count
            else f"{evidence_count} signal{'s' if evidence_count != 1 else ''} found"
        )
        items.append(
            f'<li style="margin:0 0 8px"><strong>{company}</strong>: {html.escape(status)}</li>'
        )
    return f"""
        <div style="padding:20px 28px;border-top:1px solid #e5e7eb">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Watchlist movement</div>
          <ul style="margin:14px 0 0;padding-left:18px;font-size:13px">{''.join(items)}</ul>
        </div>"""


def _problem_briefs_html(discovered: list[Record], site_url: str) -> str:
    """HTML counterpart of _problem_briefs_section / _problem_brief_block."""
    if not discovered:
        return """
        <div style="padding:20px 28px;border-top:1px solid #e5e7eb">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Problem briefs</div>
          <div style="margin-top:8px;font-size:13px;color:#6b7375">No companies cleared deep research today.</div>
        </div>"""

    blocks: list[str] = []
    for company in discovered:
        name = html.escape(str(company.get("company") or "Unknown"))
        deep_research = company.get("deep_problem_research") or {}
        prompt_gen = company.get("prompt_generation") or {}
        contact = company.get("selected_contact") or {}
        outreach = company.get("outreach") or {}

        signal_items = "".join(
            f'<li style="margin:0 0 6px">&ldquo;{html.escape(str(s.get("text", "")))}&rdquo; &mdash; '
            f'<a href="{html.escape(str(s.get("url", "")) or site_url, quote=True)}" style="color:#6366f1">source</a></li>'
            for s in (deep_research.get("observed_signals") or [])
            if s.get("text") and s.get("url")
        )
        signals_html = (
            f'<ul style="margin:8px 0 0;padding-left:18px;font-size:12px">{signal_items}</ul>'
            if signal_items
            else '<div style="margin-top:8px;font-size:12px;color:#8b9294">(No signals observed)</div>'
        )

        hypothesis = html.escape(str(deep_research.get("problem_hypothesis") or ""))
        hypothesis_html = (
            f'<div style="margin-top:10px;font-size:12px"><strong>Inference (not verified):</strong> {hypothesis}</div>'
            if hypothesis
            else ""
        )

        prompt_text = prompt_gen.get("prompt_text", "")
        if prompt_text:
            prompt_html = (
                f'<pre style="margin-top:8px;padding:10px;background:#f5f5f5;border-radius:8px;'
                f'font-size:11px;white-space:pre-wrap;overflow-wrap:break-word">{html.escape(prompt_text)}</pre>'
            )
        elif prompt_gen.get("llm_status") == "blocked_validation" and prompt_gen.get(
            "validation_errors"
        ):
            errors_html = "".join(
                f"<li>{html.escape(str(e))}</li>" for e in prompt_gen["validation_errors"]
            )
            prompt_html = (
                '<div style="margin-top:8px;font-size:12px;color:#8b9294">'
                "A prompt was generated but failed a quality check, so it is withheld:"
                f'<ul style="margin:4px 0 0;padding-left:18px">{errors_html}</ul></div>'
            )
        elif prompt_gen.get("llm_status") == "skipped_unsupported_hypothesis":
            prompt_html = (
                '<div style="margin-top:8px;font-size:12px;color:#8b9294">'
                "A real page or post was found, but it did not support an internal-problem "
                "hypothesis, so no prototype was generated -- the pipeline correctly refused "
                "to invent a problem from thin evidence.</div>"
            )
        else:
            prompt_html = (
                '<div style="margin-top:8px;font-size:12px;color:#8b9294">'
                "*Prompt not generated -- insufficient evidence.*</div>"
            )

        contact_lines = []
        if contact.get("name"):
            contact_lines.append(f"Name: {html.escape(str(contact['name']))}")
        if contact.get("email"):
            contact_lines.append(f"Email: {html.escape(str(contact['email']))}")
        if contact.get("linkedin"):
            contact_lines.append(f"LinkedIn: {html.escape(str(contact['linkedin']))}")
        if contact.get("source_url"):
            contact_lines.append(f"Source: {html.escape(str(contact['source_url']))}")
        if contact.get("access_date"):
            contact_lines.append(f"Accessed: {html.escape(str(contact['access_date']))}")
        contact_html = (
            f'<div style="margin-top:10px;font-size:12px;color:#6b7375">{" &middot; ".join(contact_lines)}</div>'
            if contact_lines
            else '<div style="margin-top:10px;font-size:12px;color:#8b9294">contact_research_required</div>'
        )

        send_status = outreach.get("send_status", "")
        validation_errors = outreach.get("validation_errors", [])
        if send_status == "blocked_insufficient_evidence":
            drafts_html = '<div style="margin-top:8px;font-size:12px;color:#8b9294">Outreach blocked: insufficient evidence.</div>'
        elif send_status == "blocked_validation":
            errs = html.escape("; ".join(validation_errors))
            drafts_html = f'<div style="margin-top:8px;font-size:12px;color:#8b9294">Outreach blocked by humanizer rules: {errs}</div>'
        else:
            parts = []
            if outreach.get("email_body"):
                parts.append(
                    f'<div style="margin-top:8px;font-size:12px"><strong>Email:</strong> {html.escape(str(outreach["email_body"]))}</div>'
                )
            if outreach.get("linkedin_note"):
                parts.append(
                    f'<div style="margin-top:6px;font-size:12px"><strong>LinkedIn note:</strong> {html.escape(str(outreach["linkedin_note"]))}</div>'
                )
            if outreach.get("linkedin_message"):
                parts.append(
                    f'<div style="margin-top:6px;font-size:12px"><strong>LinkedIn message:</strong> {html.escape(str(outreach["linkedin_message"]))}</div>'
                )
            drafts_html = "".join(parts)

        blocks.append(
            f"""
        <div style="padding:18px 28px;border-top:1px solid #e5e7eb">
          <div style="font-size:14px;font-weight:600;color:#2a2e33">{name}</div>
          {signals_html}
          {hypothesis_html}
          {prompt_html}
          {contact_html}
          {drafts_html}
        </div>"""
        )

    return f"""
        <div style="padding:20px 28px 4px;border-top:1px solid #e5e7eb">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Problem briefs</div>
        </div>{''.join(blocks)}"""


def render_html_digest(run: Record) -> str:
    """Render the personal decision digest in Rise's existing visual language."""

    site_url = os.getenv("PERSONAL_HUNT_URL", "https://rise-web-kappa.vercel.app/my-hunt")
    records = list(run.get("digest_primary", [])) + list(
        run.get("digest_remote_fallback", [])
    )
    rows: list[str] = []
    for item in records:
        company = html.escape(str(item.get("company") or ""))
        title = html.escape(str(item.get("title") or "Internship"))
        location = html.escape(str(item.get("location") or ""))
        resume = html.escape(str(item.get("resume") or "Daksh-Jain-Master"))
        score = html.escape(str(item.get("score") or "—"))
        fit = html.escape(str(item.get("llm_fit_score") or "—"))
        target = html.escape(
            str(item.get("apply_url") or item.get("source_url") or site_url),
            quote=True,
        )
        source = html.escape(str(item.get("source_url") or target), quote=True)
        rows.append(
            f"""
            <tr>
              <td style="padding:18px 20px;border-top:1px solid #e5e7eb;vertical-align:top">
                <div style="font-size:16px;font-weight:600;color:#2a2e33">{title}</div>
                <div style="margin-top:4px;font-size:14px;color:#6b7375">{company} · {location}</div>
                <div style="margin-top:8px;font-size:12px;color:#6b7375">Score {score}/100 · Kimi fit {fit}/100 · {resume}</div>
                <div style="margin-top:10px;font-size:13px"><a href="{source}" style="color:#6366f1;text-decoration:none">View source</a></div>
              </td>
              <td style="padding:18px 20px;border-top:1px solid #e5e7eb;text-align:right;vertical-align:middle;white-space:nowrap">
                <a href="{target}" style="display:inline-block;border-radius:999px;background:#6366f1;color:#fff;padding:9px 14px;font-size:13px;font-weight:600;text-decoration:none">Apply</a>
              </td>
            </tr>"""
        )

    unverified: list[str] = []
    for item in run.get("needs_verification", []):
        company = html.escape(str(item.get("company") or ""))
        title = html.escape(str(item.get("title") or "Internship"))
        location = html.escape(str(item.get("location") or ""))
        url = html.escape(
            str(item.get("apply_url") or item.get("source_url") or site_url), quote=True
        )
        unverified.append(
            f"<li style=\"margin:0 0 12px\"><a href=\"{url}\" style=\"color:#2a2e33;font-weight:600;text-decoration:none\">{title}</a>"
            f"<div style=\"margin-top:3px;color:#6b7375\">{company}"
            + (f" · {location}" if location else "")
            + "</div></li>"
        )
    worth_a_look_items: list[str] = []
    for item in _worth_a_look_records(run):
        company = html.escape(str(item.get("company") or ""))
        title = html.escape(str(item.get("title") or "Internship"))
        fit = html.escape(str(item.get("llm_fit_score") or "—"))
        reason = html.escape(str(item.get("llm_rank_reason") or ""))
        url = html.escape(
            str(item.get("apply_url") or item.get("source_url") or site_url), quote=True
        )
        worth_a_look_items.append(
            f'<li style="margin:0 0 12px"><a href="{url}" style="color:#2a2e33;font-weight:600;text-decoration:none">{title}</a>'
            f'<div style="margin-top:3px;color:#6b7375">{company} &middot; fit {fit}/100</div>'
            f'<div style="margin-top:3px;color:#8b9294">{reason}</div></li>'
        )
    worth_a_look_block = ""
    if worth_a_look_items:
        worth_a_look_block = f"""
        <div style="padding:20px 28px;border-top:1px solid #e5e7eb;background:#fafafa">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Worth a look &middot; fit 60-69, not counted toward the daily five</div>
          <ul style="margin:14px 0 0;padding-left:18px;font-size:13px">{''.join(worth_a_look_items)}</ul>
        </div>"""

    unverified_block = ""
    if unverified:
        unverified_block = f"""
        <div style="padding:20px 28px;border-top:1px solid #e5e7eb;background:#fafafa">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Needs your verification &middot; {len(unverified)} unverified lead{'s' if len(unverified) != 1 else ''}</div>
          <div style="margin-top:6px;font-size:12px;color:#8b9294">LinkedIn links this pipeline may not open. Not approved matches, and not counted above.</div>
          <ul style="margin:14px 0 0;padding-left:18px;font-size:13px">{''.join(unverified)}</ul>
        </div>"""

    signals: list[str] = []
    for event in (list(run.get("funding_primary", [])) + list(run.get("funding_extended", [])))[:2]:
        company = html.escape(str(event.get("company") or ""))
        headline = html.escape(str(event.get("headline") or "New funding signal"))
        url = html.escape(str(event.get("source_url") or site_url), quote=True)
        problem = event.get("problem_research") or {}
        hypothesis = html.escape(str(problem.get("problem_hypothesis") or ""))
        detail = f"<div style=\"margin-top:5px;color:#6b7375\">Inference to validate: {hypothesis}</div>" if hypothesis else ""
        signals.append(
            f"<li style=\"margin:0 0 12px\"><a href=\"{url}\" style=\"color:#2a2e33;font-weight:600;text-decoration:none\">{company}</a><div style=\"margin-top:3px;color:#6b7375\">{headline}</div>{detail}</li>"
        )
    signal_block = ""
    if signals:
        signal_block = f"""
        <div style="padding:20px 28px;border-top:1px solid #e5e7eb">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Funding and problem signals</div>
          <ul style="margin:14px 0 0;padding-left:18px;font-size:13px">{''.join(signals)}</ul>
        </div>"""

    target_items: list[str] = []
    for item in run.get("weekly_targets", []):
        company = html.escape(str(item.get("company") or ""))
        url = html.escape(str(item.get("company_url") or site_url), quote=True)
        target_items.append(
            f'<li style="margin:0 0 10px"><a href="{url}" style="color:#2a2e33;font-weight:600;text-decoration:none">{company}</a></li>'
        )
    weekly_block = ""
    if target_items:
        weekly_block = f"""
        <div style="padding:20px 28px;border-top:1px solid #e5e7eb;background:#fafafa">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Weekly founder targets &middot; separate manual queue</div>
          <ul style="margin:14px 0 0;padding-left:18px;font-size:13px">{''.join(target_items)}</ul>
        </div>"""

    queue_items: list[str] = []
    for item in run.get("send_queue", []) or []:
        company = html.escape(str(item.get("company") or ""))
        title = html.escape(str(item.get("title") or "Internship"))
        target = html.escape(str(item.get("apply_url") or site_url), quote=True)
        queue_items.append(
            f'<li style="margin:0 0 10px"><a href="{target}" style="color:#2a2e33;font-weight:600;text-decoration:none">{title}</a>'
            f'<div style="margin-top:3px;color:#6b7375">{company} · waiting {item.get("age_days", 0)}d</div></li>'
        )
    streak = int(run.get("send_streak_days", 0) or 0)
    queue_block = ""
    if queue_items:
        queue_block = f"""
        <div style="padding:20px 28px;border-top:1px solid #e5e7eb;background:#f5f3ff">
          <div style="font-size:13px;font-weight:600;color:#2a2e33">Today's send queue &middot; streak {streak}d &middot; manual sends win internships</div>
          <ul style="margin:14px 0 0;padding-left:18px;font-size:13px">{''.join(queue_items)}</ul>
        </div>"""

    discovered = run.get("discovered_for_research", [])
    watchlist_html = _watchlist_movement_html(discovered)
    problem_briefs_html = _problem_briefs_html(discovered, site_url)

    count = len(records)
    return f"""<!doctype html>
<html><body style="margin:0;background:#f5f5f5;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#2a2e33">
  <div style="display:none;max-height:0;overflow:hidden">{count} new high-fit internships selected for manual review.</div>
  <div style="max-width:640px;margin:28px auto;padding:0 12px">
    <div style="overflow:hidden;border:1px solid #e5e7eb;border-radius:16px;background:#fff">
      <div style="padding:26px 28px 20px">
        <div style="font-size:24px;font-weight:600;color:#6366f1">Rise</div>
        <div style="margin-top:7px;font-size:18px;font-weight:600">Your internship hunt</div>
        <div style="margin-top:5px;font-size:14px;color:#6b7375">{html.escape(str(run.get('run_date') or ''))} · {count} new match{'es' if count != 1 else ''}</div>
      </div>
      <table role="presentation" style="width:100%;border-collapse:collapse">{''.join(rows)}</table>
      {worth_a_look_block}
      {watchlist_html}
      {problem_briefs_html}
      {queue_block}
      {unverified_block}
      {weekly_block}
      {signal_block}
      <div style="padding:22px 28px;border-top:1px solid #e5e7eb">
        <a href="{html.escape(site_url, quote=True)}" style="display:inline-block;border-radius:999px;background:#2a2e33;color:#fff;padding:11px 18px;font-size:14px;font-weight:600;text-decoration:none">Open my hunt</a>
        <div style="margin-top:14px;font-size:12px;line-height:18px;color:#8b9294">Research leads only. Verify every source and send applications or outreach manually.</div>
      </div>
    </div>
  </div>
</body></html>"""
def send_self_digest(subject: str, body: str, html_body: str = "") -> str:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_json = os.getenv("GMAIL_TOKEN_JSON", "")
    token_file = os.getenv("GMAIL_TOKEN_FILE", "")
    recipient = os.getenv("GMAIL_DIGEST_TO", "")
    if not (token_json or token_file) or not recipient:
        raise RuntimeError(
            "GMAIL_TOKEN_JSON or GMAIL_TOKEN_FILE, plus GMAIL_DIGEST_TO, are required"
        )
    info = (
        json.loads(token_json)
        if token_json
        else json.loads(Path(token_file).read_text(encoding="utf-8"))
    )
    credentials = Credentials.from_authorized_user_info(info)
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return str(result["id"])


def write_digest(path: Path, run: Record) -> str:
    body = render_digest(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.with_suffix(".html").write_text(render_html_digest(run), encoding="utf-8")
    return body
