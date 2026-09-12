from __future__ import annotations

import html
import re
import time
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests

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
)


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


def _company_from_title(title: str) -> str:
    cleaned = re.sub(r"^(exclusive|funding alert)\s*[:\-]\s*", "", title, flags=re.I)
    startup_match = re.search(
        r"\bstartup\s+(.+?)\s+(?:raises?|raised|secures?|secured|bags?|closes?)\b",
        cleaned,
        flags=re.I,
    )
    if startup_match:
        company = clean_text(startup_match.group(1)).strip(" :-–—")
        if 1 <= len(company.split()) <= 12:
            return company
    match = re.match(
        r"(.+?)\s+(?:raises?|raised|secures?|secured|bags?|closes?|receives?)\b",
        cleaned,
        flags=re.I,
    )
    if not match:
        return ""
    company = clean_text(match.group(1)).strip(" :-–—")
    return company if 1 <= len(company.split()) <= 12 else ""


def parse_funding_feed(content: bytes, source: dict[str, Any]) -> list[Record]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"invalid funding feed: {parsed.bozo_exception}")
    output: list[Record] = []
    for entry in parsed.entries:
        title = repair_mojibake(html.unescape(clean_text(entry.get("title"))))
        if not title or not _funding_title(title):
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
                "funding_event_id": stable_id(
                    company, published, title, prefix="funding"
                ),
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
                "source_reported_detail": summary[:1000],
                "corroborating_urls": [source_url],
            }
        )
    return output


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
            if source.get("adapter") != "funding_rss":
                raise ValueError(f"unknown funding adapter: {source.get('adapter')}")
            response = _request(session, source["url"], timeout)
            parsed = parse_funding_feed(response.content, source)
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
            error_type, action = (
                classify_http_failure(status_code)
                if status_code
                else (
                    type(exc).__name__,
                    "Inspect the dated funding-feed contract; do not widen the window.",
                )
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


def select_funding_events(
    records: list[Record], run_date: date, scoring: dict[str, Any]
) -> tuple[list[Record], list[Record], list[Record]]:
    primary_days = int(scoring.get("funding_primary_age_days", 15))
    extension_days = int(scoring.get("funding_extension_age_days", 30))
    primary_min = int(scoring.get("funding_primary_min_items", 3))
    max_items = int(scoring.get("funding_max_items", 5))
    deduped: dict[tuple[str, str], Record] = {}
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
        event["age_days"] = age_days
        if age_days < 0:
            event["rejection_reason"] = "funding_event_future_date"
            excluded.append(event)
            continue
        if age_days > extension_days:
            event["rejection_reason"] = "funding_event_over_30_days"
            excluded.append(event)
            continue
        key = (clean_text(event.get("company")).casefold(), str(event["event_date"]))
        if key in deduped:
            existing = deduped[key]
            urls = list(existing.get("corroborating_urls") or [])
            for url in event.get("corroborating_urls") or [event.get("source_url")]:
                if url and url not in urls:
                    urls.append(url)
            existing["corroborating_urls"] = urls
            continue
        event["funding_window"] = (
            "primary_15d" if age_days <= primary_days else "extended_30d"
        )
        deduped[key] = event

    ordered = sorted(
        deduped.values(),
        key=lambda item: (
            int(item.get("age_days", 10_000)),
            clean_text(item.get("company")).casefold(),
            str(item.get("funding_event_id", "")),
        ),
    )
    primary = [item for item in ordered if item["funding_window"] == "primary_15d"]
    extension = [item for item in ordered if item["funding_window"] == "extended_30d"]
    chosen_primary = primary[:max_items]
    chosen_extension: list[Record] = []
    if len(chosen_primary) < primary_min:
        chosen_extension = extension[: max(0, max_items - len(chosen_primary))]
    return chosen_primary, chosen_extension, excluded

