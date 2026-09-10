from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup

from models import Record, clean_text, utc_timestamp
from source_health import SourceHealth, classify_http_failure


class SourceAccessError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def _rise_sheet(content: str, source: dict[str, Any]) -> list[Record]:
    """Read Rise's live Sheet directly; never use the website seed fallback."""

    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return []
    headers = {clean_text(value): index for index, value in enumerate(rows[0])}
    required = {"Title", "HiringOrganization", "Post URL", "Date Added"}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError(f"Rise Sheet contract missing headers: {', '.join(missing)}")

    def value(row: list[str], name: str) -> str:
        index = headers.get(name)
        return clean_text(row[index]) if index is not None and index < len(row) else ""

    output: list[Record] = []
    for row in rows[1:]:
        title = value(row, "Title")
        company = value(row, "HiringOrganization")
        if not title or not company:
            continue
        post_url = value(row, "Post URL")
        apply_url = value(row, "Apply Link") or post_url
        is_linkedin = "linkedin.com" in post_url.casefold() or "lnkd.in" in post_url.casefold()
        output.append(
            {
                "_source_id": source["id"],
                "_source_url": post_url,
                "source": source["id"],
                "company": company,
                "title": title,
                "description": value(row, "Description"),
                "location": value(row, "Location"),
                "work_mode": value(row, "Type"),
                "employment_type": value(row, "Timing"),
                "stipend": value(row, "Stipend"),
                "duration": value(row, "Duration"),
                "contact_email": value(row, "Contact Email"),
                "source_url": post_url,
                "apply_url": apply_url,
                "posted_at": value(row, "PostedDate") or value(row, "Date Added"),
                "source_confidence": "low" if is_linkedin else "medium",
                "verification_status": (
                    "machine_collected_unverified" if is_linkedin else "machine_collected"
                ),
                "source_priority": source.get("source_priority", 99),
            }
        )
    return output


def _request(
    session: requests.Session,
    url: str,
    timeout: int,
    attempts: int = 3,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code in {401, 403}:
                raise SourceAccessError(response.status_code, f"access blocked: {url}")
            if response.status_code == 429 or response.status_code >= 500:
                last_error = SourceAccessError(response.status_code, "temporary HTTP error")
                if attempt + 1 < attempts:
                    time.sleep(min(2**attempt, 4))
                    continue
            response.raise_for_status()
            return response
        except (requests.RequestException, SourceAccessError) as exc:
            last_error = exc
            if isinstance(exc, SourceAccessError) and exc.status_code in {401, 403}:
                raise
            if attempt + 1 < attempts:
                time.sleep(min(2**attempt, 4))
    if last_error:
        raise last_error
    raise RuntimeError("request failed without an exception")


def _ftb(payload: Any, source: dict[str, Any]) -> list[Record]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next(
            (
                payload[key]
                for key in ("internships", "data", "results", "items")
                if isinstance(payload.get(key), list)
            ),
            [],
        )
    else:
        rows = []
    output: list[Record] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.update(
            {
                "_source_id": source["id"],
                "_source_url": source["url"],
                "source": source["id"],
                "source_url": row.get("link") or source["url"],
                "source_confidence": "official",
                "source_priority": source.get("source_priority", 99),
            }
        )
        output.append(row)
    return output


def _wwr(content: bytes, source: dict[str, Any]) -> list[Record]:
    parsed = feedparser.parse(content)
    output: list[Record] = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title"))
        company, separator, role = title.partition(":")
        output.append(
            {
                "_source_id": source["id"],
                "_source_url": source["url"],
                "source": source["id"],
                "id": clean_text(entry.get("id") or entry.get("link")),
                "company": clean_text(company) if separator else "",
                "title": clean_text(role) if separator else title,
                "description": clean_text(
                    entry.get("summary") or entry.get("description")
                ),
                "location": "Remote - worldwide",
                "work_mode": "remote",
                "link": entry.get("link"),
                "source_url": entry.get("link"),
                "source_confidence": "official",
                "posted_at": entry.get("published") or entry.get("updated"),
                "source_priority": source.get("source_priority", 99),
            }
        )
    return output


def _replace_query(url: str, **updates: Any) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in updates.items()})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _fetch_ftb_paginated(
    session: requests.Session, source: dict[str, Any], timeout: int
) -> list[Record]:
    page_size = int(source.get("page_size", 100))
    max_pages = int(source.get("max_pages", 5))
    output: list[Record] = []
    for page in range(max_pages):
        url = _replace_query(source["url"], limit=page_size, offset=page * page_size)
        response = _request(session, url, timeout)
        page_source = {**source, "url": url}
        records = _ftb(response.json(), page_source)
        output.extend(records)
        if len(records) < page_size:
            break
    return output


def _yc(content: str, source: dict[str, Any]) -> list[Record]:
    soup = BeautifulSoup(content, "html.parser")
    output: list[Record] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href*="/companies/"][href*="/jobs/"]'):
        href = str(anchor.get("href") or "")
        if not re.match(r"^/companies/[^/]+/jobs/[^/]+$", href):
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title or href in seen:
            continue
        seen.add(href)
        url = href if href.startswith("http") else f"https://www.ycombinator.com{href}"
        card = anchor.find_parent("li")
        card_text = clean_text(card.get_text(" ", strip=True) if card else title)
        company_span = card.select_one("span.block.font-bold") if card else None
        company_text = clean_text(company_span.get_text(" ", strip=True)) if company_span else ""
        if not company_text and card:
            for candidate in card.select('a[href^="/companies/"]:not([href*="/jobs/"])'):
                company_text = clean_text(candidate.get_text(" ", strip=True))
                if company_text:
                    break
        company = re.sub(r"\s*\([A-Z]\d+\)\s*$", "", company_text).strip()
        location = "Bengaluru"
        if "bangalore" in card_text.casefold():
            location = "Bangalore"
        output.append(
            {
                "_source_id": source["id"],
                "_source_url": source["url"],
                "source": source["id"],
                "id": href,
                "company": company,
                "title": title,
                "description": card_text,
                "location": location,
                "work_mode": "onsite",
                "link": url,
                "source_url": url,
                "source_confidence": "official",
                "source_priority": source.get("source_priority", 99),
            }
        )
    return output


def _wellfound(content: str, source: dict[str, Any]) -> list[Record]:
    soup = BeautifulSoup(content, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if not next_data or not next_data.string:
        raise ValueError("Wellfound public page has no __NEXT_DATA__ contract")
    payload = json.loads(next_data.string)
    data = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("apolloState", {})
        .get("data", {})
    )
    if not isinstance(data, dict):
        raise ValueError("Wellfound Apollo state is missing")
    company_by_job: dict[str, dict[str, Any]] = {}
    for value in data.values():
        if not isinstance(value, dict):
            continue
        references = value.get("highlightedJobListings")
        if not isinstance(references, list):
            continue
        for reference in references:
            if isinstance(reference, dict) and reference.get("__ref"):
                company_by_job[str(reference["__ref"])] = value
    output: list[Record] = []
    for key, item in data.items():
        if not str(key).startswith("JobListingSearchResult:") or not isinstance(item, dict):
            continue
        company = company_by_job.get(str(key), {})
        job_id = clean_text(item.get("id"))
        slug = clean_text(item.get("slug"))
        url = f"https://wellfound.com/jobs/{job_id}-{slug}" if job_id and slug else source["url"]
        timestamp = item.get("liveStartAt")
        posted_at = ""
        if isinstance(timestamp, (int, float)):
            posted_at = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        locations = item.get("locationNames")
        location = ", ".join(clean_text(value) for value in locations) if isinstance(
            locations, list
        ) else clean_text(locations)
        remote_config = item.get("remoteConfig") if isinstance(
            item.get("remoteConfig"), dict
        ) else {}
        output.append(
            {
                "_source_id": source["id"],
                "_source_url": source["url"],
                "source": source["id"],
                "id": job_id,
                "company": clean_text(company.get("name")),
                "company_url": (
                    f"https://wellfound.com/company/{company.get('slug')}"
                    if company.get("slug")
                    else ""
                ),
                "company_size": clean_text(company.get("companySize")),
                "title": clean_text(item.get("title")),
                "description": clean_text(item.get("description")),
                "location": location,
                "work_mode": clean_text(remote_config.get("kind"))
                or ("remote" if item.get("remote") else "onsite"),
                "employment_type": clean_text(item.get("jobType")),
                "link": url,
                "source_url": url,
                "posted_at": posted_at,
                "source_confidence": "official",
                "verification_status": "machine_collected",
                "source_priority": source.get("source_priority", 99),
            }
        )
    return output


def fetch_live(config: dict[str, Any]) -> tuple[list[Record], list[Record]]:
    session = requests.Session()
    session.headers["User-Agent"] = config.get("user_agent", "InternshipResearch/0.1")
    timeout = int(config.get("timeout_seconds", 25))
    all_records: list[Record] = []
    health: list[Record] = []

    for source in config.get("sources", []):
        if not source.get("enabled") or source.get("adapter") == "human_import":
            continue
        started = time.perf_counter()
        try:
            if source["adapter"] == "rise_sheet":
                sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
                if not sheet_id:
                    raise RuntimeError("GOOGLE_SHEET_ID is required for the Rise Sheet source")
                url = (
                    f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
                    "?format=csv&gid=0"
                )
                response = _request(session, url, timeout)
                records = _rise_sheet(response.text, {**source, "url": url})
            elif source["adapter"] == "ftb":
                records = _fetch_ftb_paginated(session, source, timeout)
            elif source["adapter"] == "wwr":
                response = _request(session, source["url"], timeout)
                records = _wwr(response.content, source)
            elif source["adapter"] == "yc":
                response = _request(session, source["url"], timeout)
                records = _yc(response.text, source)
            elif source["adapter"] == "wellfound":
                response = _request(session, source["url"], timeout)
                records = _wellfound(response.text, source)
            elif str(source["adapter"]).startswith("apify_"):
                from apify_sources import fetch_apify_actor

                records, apify_metadata = fetch_apify_actor(
                    source, config.get("apify", {}), timeout
                )
            else:
                raise ValueError(f"unknown enabled adapter: {source['adapter']}")
            all_records.extend(records)
            event = SourceHealth(
                    source_id=source["id"],
                    status="ok" if records else "zero_results",
                    record_count=len(records),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ).to_dict()
            if str(source["adapter"]).startswith("apify_"):
                health_status = apify_metadata.pop("health_status", event["status"])
                event.update(apify_metadata)
                event["status"] = health_status
            health.append(event)
        except Exception as exc:
            status_code = int(getattr(exc, "status_code", 0) or 0)
            error_type, action = classify_http_failure(status_code) if status_code else (
                type(exc).__name__,
                "Inspect logs and the dated public source contract.",
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
    return all_records, health


def load_json_records(path: Path, source_id: str = "human_import") -> list[Record]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload.get("records", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a list or a records list")
    output: list[Record] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("source", source_id)
        item.setdefault("source_confidence", "high" if source_id == "human_import" else "medium")
        item.setdefault("verification_status", "human_verified" if source_id == "human_import" else "fixture")
        output.append(item)
    return output


def fixture_health(count: int) -> list[Record]:
    return [
        SourceHealth(
            source_id="fixture",
            status="ok",
            record_count=count,
            checked_at=utc_timestamp(),
        ).to_dict()
    ]
