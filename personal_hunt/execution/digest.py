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
    else:
        lines.append("- Yield: no source activity recorded.")
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
    return "\n".join(
        [
            f"# Internship hunt digest - {run['run_date']}",
            "",
            f"**{label}**",
            "",
            (
                f"Internships: prior {run.get('internship_window_days', 10)} days. "
                f"Funding: primary {run.get('funding_primary_window_days', 15)} days; "
                f"labeled extension through {run.get('funding_extension_window_days', 30)} days."
            ),
            "",
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
            _verification_section(run.get("needs_verification", [])),
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
