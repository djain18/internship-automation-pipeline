from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import feedparser
import requests
from bs4 import BeautifulSoup

from company_resolve import is_roundup_headline
from fetch_sources import _request
from models import Record, canonical_url, clean_text, repair_mojibake, stable_id
from source_health import SourceHealth, classify_http_failure


FUNDING_TERMS = (
    " raises ",
    " raised ",
    " secures ",
    " secured ",
    " funding ",
    " funding round",
    " seed round",
    " pre-seed",
    " series a",
    " series b",
    " investment from",
    " backed by",
    " leads ",
)

# A listed company's IPO, anchor book or block deal is not a startup raise and
# never a Founder's Office internship target. Checked against the Entrackr
# feed of 2026-09-22 ("NSE raises Rs 6,746 Cr from anchor investors ahead of IPO").
NOT_A_RAISE = re.compile(r"\b(ipo|anchor investors?|bulk deal|block deal|drhp|rhp)\b", re.I)
# "<descriptor> startup/brand/platform X raises": the name follows the noun.
_DESCRIPTOR = r"\b(?:startup|brand|platform|company|firm|maker|marketplace|app)"
_RAISE_VERB = r"(?:raises?|raised|secures?|secured|bags?|closes?)\b"
_ROUND_TYPES = (
    ("pre-series a", "Pre-Series A"),
    ("pre-seed", "Pre-Seed"),
    ("seed", "Seed"),
    ("series a", "Series A"),
    ("series b", "Series B"),
    ("series c", "Series C"),
    ("series d", "Series D"),
    ("series e", "Series E"),
    ("debt", "Debt"),
    ("bridge", "Bridge"),
)


_AMOUNT = re.compile(r"(?:rs\.?|inr|\$|₹)\s?[\d.,]+(?:\s?(?:cr|crore|mn|million|bn|billion|k|lakh)\b)?", re.I)


def _amount(text: str) -> str:
    match = _AMOUNT.search(clean_text(text))
    return match.group(0).strip() if match else ""


def _round_type(text: str) -> str:
    lowered = f" {clean_text(text).casefold()} "
    for term, label in _ROUND_TYPES:
        if re.search(rf"(?<![a-z-]){re.escape(term)}\b", lowered):
            return label
    return ""


def _event_date(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        try:
            return parsedate_to_datetime(text).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return ""


def _funding_title(title: str) -> bool:
    padded = f" {title.casefold()} "
    return any(term in padded for term in FUNDING_TERMS)


def _tidy_company(value: str) -> str:
    company = clean_text(value).strip(" :-–—")
    # "Disha (formerly Curelink)" -> "Disha"; "Drivn’s Indian entity" -> "Drivn".
    company = re.sub(r"\s*\(.*?\)\s*", " ", company).strip()
    company = re.sub(r"[’']s\s+(?:indian\s+)?(?:entity|arm|unit|subsidiary)$", "", company, flags=re.I)
    return company if 1 <= len(company.split()) <= 12 else ""


def _company_from_title(title: str) -> str:
    cleaned = re.sub(r"^(exclusive|funding alert)\s*[:\-]\s*", "", title, flags=re.I)
    # "Info Edge leads Rs 8.9 Cr seed round in Factrika" and
    # "Avaana Capital leads Rs 43 Cr round in deeptech company DheyaTech".
    led = re.search(r"\bleads?\b.*?\bround\s+in\s+(.+)$", cleaned, flags=re.I)
    if led:
        target = led.group(1)
        named = re.search(rf"{_DESCRIPTOR}\s+(.+)$", target, flags=re.I)
        return _tidy_company(named.group(1) if named else target)
    if not re.search(rf"\b{_RAISE_VERB}|\breceives?\b", cleaned, flags=re.I):
        return ""
    descriptor_match = re.search(rf"{_DESCRIPTOR}\s+(.+?)\s+{_RAISE_VERB}", cleaned, flags=re.I)
    if descriptor_match:
        company = _tidy_company(descriptor_match.group(1))
        if company:
            return company
    match = re.match(rf"(.+?)\s+(?:{_RAISE_VERB}|receives?\b)", cleaned, flags=re.I)
    return _tidy_company(match.group(1)) if match else ""


def company_key(value: Any) -> str:
    return "".join(character for character in clean_text(value).casefold() if character.isalnum())


def funding_event_id(company: str) -> str:
    """One id per company, whichever outlet reported the raise first, so the
    Outbox lead id stays the same when a later report merges in."""
    return stable_id(company_key(company), prefix="funding")


def parse_funding_feed(content: bytes, source: dict[str, Any]) -> list[Record]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"invalid funding feed: {parsed.bozo_exception}")
    output: list[Record] = []
    for entry in parsed.entries:
        title = repair_mojibake(html.unescape(clean_text(entry.get("title"))))
        if not title or not _funding_title(title) or NOT_A_RAISE.search(title):
            continue
        if is_roundup_headline(title):
            # A weekly/period roundup names many companies; treating the
            # first regex-matched name as "the" company would misattribute
            # the whole roundup's evidence to one of them.
            continue
        company = _company_from_title(title)
        published = _event_date(entry.get("published") or entry.get("updated"))
        source_url = canonical_url(entry.get("link"))
        if not company or not published or not source_url:
            continue
        summary = repair_mojibake(
            html.unescape(clean_text(entry.get("summary") or entry.get("description")))
        )
        output.append(
            {
                "funding_event_id": funding_event_id(company),
                "company": company,
                "event_date": published,
                "event_date_basis": "source_publication_date",
                "headline": title,
                "source_name": source["name"],
                "source_id": source["id"],
                "source_url": source_url,
                "accessed_at": date.today().isoformat(),
                "source_confidence": source.get("source_confidence", "medium"),
                "verification_status": "press_reported_unverified",
                "source_reported_detail": summary[:1500],
                "round_type": _round_type(title),
                "amount": _amount(title),
                "corroborating_urls": [source_url],
            }
        )
    return output


# Inc42 "Funding Galore" table headers, matched case-insensitively. Checked on
# the 2026-09-19 roundup: Date, Name, Sector, Subsector, Business Model,
# Funding Round Size, Funding Round Type, Investors, Lead Investor.
_ROUNDUP_COLUMNS = {
    "date": "row_date",
    "name": "company",
    "sector": "sector",
    "subsector": "subsector",
    "business model": "business_model",
    "funding round size": "amount",
    "funding round type": "round_type",
    "investors": "investors",
    "lead investor": "lead_investor",
}


class RoundupFormatChanged(ValueError):
    """A roundup exists but its startup table could not be read."""


def _roundup_rows(html_text: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [
            clean_text(cell.get_text(" ", strip=True)).casefold()
            for cell in rows[0].find_all(["th", "td"])
        ]
        if "name" not in headers:
            continue
        output: list[dict[str, str]] = []
        for row in rows[1:]:
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
            item = {
                _ROUNDUP_COLUMNS[header]: repair_mojibake(value)
                for header, value in zip(headers, cells)
                if header in _ROUNDUP_COLUMNS
            }
            # Empty cells are printed as a dash or a stray replacement glyph.
            item = {key: value for key, value in item.items() if re.search(r"[A-Za-z0-9]", value)}
            # The footer ("Source: Inc42 ...") is a one-cell row with no date.
            if item.get("company") and (item.get("row_date") or item.get("amount")):
                output.append(item)
        return output
    return []


def parse_funding_roundup_feed(
    content: bytes, source: dict[str, Any], newest_roundups: int = 3
) -> list[Record]:
    """One event per startup row of the newest weekly roundups.

    Each row is its own raise with its own amount and investors, so the
    misattribution that makes roundup headlines unusable does not apply: the
    headline is never parsed, only the table. The row's Date column is the
    event date.
    """
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"invalid funding feed: {parsed.bozo_exception}")
    output: list[Record] = []
    unreadable: list[str] = []
    for entry in parsed.entries[:newest_roundups]:
        source_url = canonical_url(entry.get("link"))
        body = " ".join(part.get("value", "") for part in entry.get("content") or [])
        rows = _roundup_rows(body)
        if not rows:
            unreadable.append(source_url)
            continue
        published = _event_date(entry.get("published") or entry.get("updated"))
        for row in rows:
            try:
                event_date = datetime.strptime(row.get("row_date", ""), "%d %b %Y").date().isoformat()
                basis = "roundup_row_date"
            except ValueError:
                event_date, basis = published, "roundup_publication_date"
            company = _tidy_company(row["company"])
            if not company or not event_date or not source_url:
                continue
            detail = "; ".join(
                f"{label}: {row[key]}"
                for key, label in (
                    ("amount", "Round size"),
                    ("round_type", "Round"),
                    ("lead_investor", "Lead investor"),
                    ("investors", "Investors"),
                    ("sector", "Sector"),
                    ("subsector", "Subsector"),
                    ("business_model", "Business model"),
                )
                if row.get(key)
            )
            amount = row.get("amount", "").rstrip("*").strip()
            output.append(
                {
                    "funding_event_id": funding_event_id(company),
                    "company": company,
                    "event_date": event_date,
                    "event_date_basis": basis,
                    "headline": f"{company} raised {amount or 'an undisclosed amount'}"
                    + (f" ({row['round_type']})" if row.get("round_type") else ""),
                    "source_name": source["name"],
                    "source_id": source["id"],
                    "source_url": source_url,
                    "accessed_at": date.today().isoformat(),
                    "source_confidence": source.get("source_confidence", "medium"),
                    "verification_status": "press_reported_unverified",
                    "source_reported_detail": detail[:1500],
                    "round_type": _round_type(row.get("round_type", "")) or row.get("round_type", ""),
                    "amount": amount,
                    "lead_investor": row.get("lead_investor", ""),
                    "sector": " / ".join(filter(None, (row.get("sector"), row.get("subsector")))),
                    "corroborating_urls": [source_url],
                }
            )
    if unreadable and not output:
        raise RoundupFormatChanged(
            f"roundup_format_changed: no startup table in {', '.join(unreadable)}"
        )
    return output


FUNDING_ADAPTERS = {
    "funding_rss": parse_funding_feed,
    "funding_roundup": parse_funding_roundup_feed,
}


def fetch_funding_live(config: dict[str, Any]) -> tuple[list[Record], list[Record]]:
    session = requests.Session()
    session.headers["User-Agent"] = config.get(
        "user_agent", "DakshInternshipResearch/0.1"
    )
    timeout = int(config.get("timeout_seconds", 25))
    records: list[Record] = []
    health: list[Record] = []
    for source in config.get("funding_sources", []):
        if not source.get("enabled"):
            continue
        started = time.perf_counter()
        try:
            parser = FUNDING_ADAPTERS.get(source.get("adapter"))
            if parser is None:
                raise ValueError(f"unknown funding adapter: {source.get('adapter')}")
            response = _request(session, source["url"], timeout)
            parsed = parser(response.content, source)
            records.extend(parsed)
            health.append(
                SourceHealth(
                    source_id=source["id"],
                    status="ok" if parsed else "zero_results",
                    record_count=len(parsed),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ).to_dict()
            )
        except Exception as exc:
            status_code = int(getattr(exc, "status_code", 0) or 0)
            if isinstance(exc, RoundupFormatChanged):
                error_type, action = (
                    "roundup_format_changed",
                    "Open the newest roundup and update _ROUNDUP_COLUMNS; do not guess rows.",
                )
            elif status_code:
                error_type, action = classify_http_failure(status_code)
            else:
                error_type, action = (
                    type(exc).__name__,
                    "Inspect the dated funding-feed contract; do not widen the window.",
                )
            health.append(
                SourceHealth(
                    source_id=source["id"],
                    status="failed",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error_type=error_type,
                    error_message=str(exc)[:500],
                    human_action=action,
                ).to_dict()
            )
        time.sleep(float(config.get("min_interval_seconds", 2)))
    return records, health


def merge_funding_events(records: list[Record]) -> list[Record]:
    """One event per company: the earliest dated report, every other
    report's URL as corroboration, and empty fields filled from the others.

    A field already set (including research a ledger copy carries) is never
    overwritten, so a fresh feed copy of the same raise cannot wipe research.
    """
    merged: dict[str, Record] = {}
    for record in sorted(records, key=lambda item: str(item.get("event_date") or "9999")):
        key = company_key(record.get("company"))
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(record)
            continue
        existing = merged[key]
        urls = list(existing.get("corroborating_urls") or [])
        for url in record.get("corroborating_urls") or [record.get("source_url")]:
            if url and url not in urls:
                urls.append(url)
        existing["corroborating_urls"] = urls
        for field, value in record.items():
            if value not in ("", None, [], {}) and existing.get(field) in ("", None, [], {}):
                existing[field] = value
        # A full article beats a table row for the city and use-of-funds text.
        if record.get("source_id") != "inc42_funding_galore" and len(
            clean_text(record.get("source_reported_detail"))
        ) > len(clean_text(existing.get("source_reported_detail"))):
            existing["source_reported_detail"] = record["source_reported_detail"]
    return list(merged.values())


def select_funding_events(
    records: list[Record], run_date: date, scoring: dict[str, Any]
) -> tuple[list[Record], list[Record]]:
    """Every company funded in the last `funding_window_days` (default 14),
    newest first, plus the excluded records with a reason."""
    window_days = int(scoring.get("funding_window_days", 14))
    kept: list[Record] = []
    excluded: list[Record] = []
    for record in records:
        event = dict(record)
        try:
            age_days = (
                run_date - datetime.fromisoformat(str(event.get("event_date"))).date()
            ).days
        except (TypeError, ValueError):
            event["rejection_reason"] = "funding_event_missing_or_invalid_date"
            excluded.append(event)
            continue
        if age_days < 0:
            event["rejection_reason"] = "funding_event_future_date"
            excluded.append(event)
            continue
        if age_days > window_days:
            event["rejection_reason"] = f"funding_event_over_{window_days}_days"
            excluded.append(event)
            continue
        kept.append(event)
    selected = merge_funding_events(kept)
    for event in selected:
        event["age_days"] = (
            run_date - datetime.fromisoformat(str(event["event_date"])).date()
        ).days
        event["funding_window"] = f"last_{window_days}d"
    selected.sort(key=lambda item: (int(item["age_days"]), clean_text(item.get("company")).casefold()))
    return selected, excluded


def load_ledger(path: Path) -> list[Record]:
    """Funding events kept between runs, with whatever research they got.

    The feeds hold one to eight days; the ledger is what makes a 14-day
    window real and keeps a researched company's problem and prompts on the
    page after the run that produced them. Same atomic-write pattern as
    outreach_store.
    """
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("events") or [])


def save_ledger(path: Path, events: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    transient = {"age_days", "rejection_reason", "funding_window"}
    payload = {"events": [{k: v for k, v in event.items() if k not in transient} for event in events]}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
