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
from normalize import classify_location
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
                "verification_status": ("machine_collected_unverified" if is_linkedin else "machine_collected"),
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
            (payload[key] for key in ("internships", "data", "results", "items") if isinstance(payload.get(key), list)),
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
                "description": clean_text(entry.get("summary") or entry.get("description")),
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


def _fetch_ftb_paginated(session: requests.Session, source: dict[str, Any], timeout: int) -> list[Record]:
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
    data = payload.get("props", {}).get("pageProps", {}).get("apolloState", {}).get("data", {})
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
        location = (
            ", ".join(clean_text(value) for value in locations)
            if isinstance(locations, list)
            else clean_text(locations)
        )
        remote_config = item.get("remoteConfig") if isinstance(item.get("remoteConfig"), dict) else {}
        output.append(
            {
                "_source_id": source["id"],
                "_source_url": source["url"],
                "source": source["id"],
                "id": job_id,
                "company": clean_text(company.get("name")),
                "company_url": (f"https://wellfound.com/company/{company.get('slug')}" if company.get("slug") else ""),
                "company_size": clean_text(company.get("companySize")),
                "title": clean_text(item.get("title")),
                "description": clean_text(item.get("description")),
                "location": location,
                "work_mode": clean_text(remote_config.get("kind")) or ("remote" if item.get("remote") else "onsite"),
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


_ATS_HOSTS = {
    "greenhouse": {"boards-api.greenhouse.io"},
    "lever": {"api.lever.co"},
    "ashby": {"api.ashbyhq.com"},
    "workable": {"apply.workable.com"},
    "teamtailor": {"careers.lyzr.ai"},  # Teamtailor instances run on company domains; expand as needed
}


def _verified_ats_url(source: dict[str, Any]) -> str:
    """Require a reviewed, source-native URL; adapters never derive company domains."""

    url = clean_text(source.get("url"))
    adapter = clean_text(source.get("adapter"))
    vendor = adapter.removesuffix("_ats")
    parts = urlsplit(url)
    if not url or parts.scheme != "https" or parts.hostname not in _ATS_HOSTS.get(vendor, set()):
        raise ValueError(f"{adapter} requires an explicit reviewed {vendor} HTTPS API URL")
    return url


def _ats_record(source: dict[str, Any], **values: Any) -> Record:
    url = clean_text(values.get("url"))
    return {
        "_source_id": source["id"],
        "_source_url": source["url"],
        "source": source["id"],
        "id": clean_text(values.get("id")) or url,
        "company": clean_text(values.get("company") or source.get("company")),
        "company_url": clean_text(source.get("company_url")),
        "title": clean_text(values.get("title")),
        "description": clean_text(values.get("description")),
        "location": clean_text(values.get("location")),
        "work_mode": clean_text(values.get("work_mode")),
        "employment_type": clean_text(values.get("employment_type")),
        "link": url,
        "source_url": url,
        "apply_url": clean_text(values.get("apply_url")) or url,
        "posted_at": values.get("posted_at") or "",
        "source_confidence": "official",
        "verification_status": "machine_collected",
        "source_priority": source.get("source_priority", 99),
    }


def _greenhouse(payload: Any, source: dict[str, Any]) -> list[Record]:
    rows = payload.get("jobs", []) if isinstance(payload, dict) else []
    output: list[Record] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        location = item.get("location") if isinstance(item.get("location"), dict) else {}
        output.append(
            _ats_record(
                source,
                id=item.get("id"),
                title=item.get("title"),
                location=location.get("name"),
                url=item.get("absolute_url"),
                posted_at=item.get("updated_at"),
                description=item.get("content"),
            )
        )
    return output


def _lever(payload: Any, source: dict[str, Any]) -> list[Record]:
    rows = payload if isinstance(payload, list) else []
    output: list[Record] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
        output.append(
            _ats_record(
                source,
                id=item.get("id"),
                title=item.get("text"),
                location=categories.get("location"),
                employment_type=categories.get("commitment"),
                work_mode=item.get("workplaceType"),
                url=item.get("hostedUrl"),
                apply_url=item.get("applyUrl"),
                posted_at=item.get("createdAt"),
                description=item.get("descriptionPlain") or item.get("description"),
            )
        )
    return output


def _ashby(payload: Any, source: dict[str, Any]) -> list[Record]:
    rows = payload.get("jobs", []) if isinstance(payload, dict) else []
    output: list[Record] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        output.append(
            _ats_record(
                source,
                id=item.get("id"),
                title=item.get("title"),
                location=item.get("location"),
                employment_type=item.get("employmentType"),
                work_mode="remote" if item.get("isRemote") else "",
                url=item.get("jobUrl"),
                apply_url=item.get("applyUrl"),
                posted_at=item.get("publishedAt"),
                description=item.get("descriptionPlain"),
            )
        )
    return output


def _workable(payload: Any, source: dict[str, Any]) -> list[Record]:
    rows = payload.get("jobs", payload.get("results", [])) if isinstance(payload, dict) else []
    output: list[Record] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        location = item.get("location")
        if isinstance(location, dict):
            location = location.get("location_str") or location.get("city")
        output.append(
            _ats_record(
                source,
                id=item.get("shortcode") or item.get("id"),
                title=item.get("title"),
                location=location,
                employment_type=item.get("employment_type"),
                work_mode=item.get("workplace"),
                url=item.get("url") or item.get("shortlink"),
                posted_at=item.get("published_on") or item.get("created_at"),
                description=item.get("description"),
            )
        )
    return output


def _teamtailor(content: bytes, source: dict[str, Any]) -> list[Record]:
    """Parse Teamtailor RSS feeds. Teamtailor instances run on company domains.

    RSS entries include standard RSS fields plus Teamtailor-specific namespaced
    fields: tt_city, tt_department, tt_name, tt_address, etc.
    """
    parsed = feedparser.parse(content)
    output: list[Record] = []
    for entry in parsed.entries:
        if not isinstance(entry, dict):
            continue
        title = clean_text(entry.get("title"))
        location = clean_text(entry.get("tt_city") or entry.get("tt_location") or entry.get("tt_name") or "")
        url = clean_text(entry.get("link"))
        if not title or not url:
            continue
        summary = clean_text(entry.get("summary", ""))
        # Extract location from HTML summary if tt_city is empty
        if not location and summary:
            # Try to extract from HTML; summary may contain location mentions
            summary_text = summary.replace("<", " ").replace(">", " ")
            if "bengaluru" in summary_text.casefold() or "bangalore" in summary_text.casefold():
                location = "Bengaluru"
        output.append(
            _ats_record(
                source,
                id=clean_text(entry.get("id")) or url,
                title=title,
                location=location,
                url=url,
                posted_at=entry.get("published") or entry.get("updated"),
                description=summary,
            )
        )
    return output


def _fetch_ats(session: requests.Session, source: dict[str, Any], timeout: int) -> list[Record]:
    url = _verified_ats_url(source)
    response = _request(session, url, timeout)
    parser = {
        "greenhouse_ats": _greenhouse,
        "lever_ats": _lever,
        "ashby_ats": _ashby,
        "workable_ats": _workable,
    }[source["adapter"]]
    return parser(response.json(), source)


# Vendor board links embedded in aggregator pages convert to the vendors' own
# public board APIs, which the adapters above already speak. Slugs come only
# from discovered links; nothing is derived from company names or guessed.
def _harvested_ats_source(vendor: str, slug: str) -> Record | None:
    slug = clean_text(slug).strip("/")
    if not slug or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", slug):
        return None
    urls = {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
    }
    url = urls.get(vendor)
    if not url:
        return None
    # The board slug is the employer's own identifier on the vendor platform
    # (e.g. celonis runs boards.greenhouse.io/celonis), so it doubles as the
    # provisional company name. Traceable via the source id, never guessed
    # from a person name or free text.
    company = slug.replace("-", " ").replace("_", " ").title()
    return {
        "id": f"ats_harvested_{vendor}_{slug}",
        "name": f"Harvested {vendor} board {slug}",
        "company": company,
        "company_url": "",
        "url": url,
        "enabled": True,
        "adapter": f"{vendor}_ats",
        "access_policy": "harvested_public_ats_api",
        "source_priority": 2,
    }


def watchlist_board_sources(watchlist_config: dict[str, Any]) -> list[Record]:
    """Convert config/watchlist.yml's per-company board_url/board_adapter into
    fetch_live-compatible source dicts, so each watchlist company's own board
    is read directly every run rather than hoping a registry surfaces it.
    Companies with no board (board_url or board_adapter empty, e.g. AEOS,
    which is bootstrapped with no ATS at all) are skipped, not guessed at."""
    output: list[Record] = []
    for company_cfg in watchlist_config.get("companies", []):
        if not isinstance(company_cfg, dict):
            continue
        board_url = clean_text(company_cfg.get("board_url", ""))
        adapter = clean_text(company_cfg.get("board_adapter", ""))
        name = clean_text(company_cfg.get("name", ""))
        if not board_url or not adapter or not name:
            continue
        slug = re.sub(r"[^A-Za-z0-9_.-]", "_", name.casefold())
        output.append(
            {
                "id": f"watchlist_{slug}",
                "name": f"Watchlist board: {name}",
                "company": name,
                "company_url": clean_text(company_cfg.get("site_url", "")),
                "url": board_url,
                "enabled": True,
                "adapter": adapter,
                "access_policy": "watchlist_configured_board",
                "source_priority": 1,
            }
        )
    return output


ATS_LINK_PATTERNS = (
    ("greenhouse", re.compile(r"https://boards\.greenhouse\.io/([A-Za-z0-9][A-Za-z0-9_.-]*)", re.I)),
    ("ashby", re.compile(r"https://jobs\.ashbyhq\.com/([A-Za-z0-9][A-Za-z0-9_.-]*)", re.I)),
    ("lever", re.compile(r"https://([A-Za-z0-9][A-Za-z0-9_-]*)\.lever\.co/", re.I)),
)


def harvest_ats_boards(text: str, max_boards: int) -> list[Record]:
    """Collect vendor board sources from links embedded in an aggregator page."""
    found: dict[str, Record] = {}
    for vendor, pattern in ATS_LINK_PATTERNS:
        for match in pattern.finditer(text or ""):
            source = _harvested_ats_source(vendor, match.group(1))
            if source is not None:
                found.setdefault(source["id"], source)
            if len(found) >= max(1, max_boards):
                return sorted(found.values(), key=lambda item: item["id"])
    return sorted(found.values(), key=lambda item: item["id"])


def _in_scope_only(records: list[Record]) -> list[Record]:
    """Drop harvested-board rows whose location is out of scope.

    A harvested board is an entire company's job board, so one global employer
    (Feverup, Socure, Illumio) can contribute hundreds of rows. On
    run_f9ae04eb99b98d0e, 955 of 1,447 deduplicated records — 66% of the whole
    pool — came from harvested boards and *every single one* was rejected for
    location_out_of_scope. Location is a hard exclusion that no later tier can
    reverse (the Tier 2 LLM read only clears role_not_cross_functional), so
    dropping it here can never discard an admissible record; it only stops the
    noise from being normalized, deduplicated, scored and reported.
    """
    return [
        record
        for record in records
        if classify_location(
            clean_text(record.get("location", "")), clean_text(record.get("work_mode", ""))
        )[0]
        != "other"
    ]


def fetch_harvested_boards(
    session: requests.Session, harvest_cfg: dict[str, Any], timeout: int, interval: float
) -> tuple[list[Record], list[Record]]:
    """Fetch aggregator pages, convert embedded vendor links, fetch each board."""
    records: list[Record] = []
    health: list[Record] = []
    if not harvest_cfg.get("enabled", False):
        return records, health
    max_boards = int(harvest_cfg.get("max_boards", 8))
    for page_url in harvest_cfg.get("pages", []):
        page_url = clean_text(page_url)
        if not page_url:
            continue
        started = time.perf_counter()
        try:
            response = _request(session, page_url, timeout)
            boards = harvest_ats_boards(response.text, max_boards)
            if not boards:
                health.append(
                    SourceHealth(
                        source_id=f"ats_harvest_page:{urlsplit(page_url).netloc}",
                        status="zero_results",
                        record_count=0,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        human_action="Aggregator page embeds no vendor board links.",
                    ).to_dict()
                )
                continue
            for board in boards:
                board_started = time.perf_counter()
                try:
                    board_records = _in_scope_only(_fetch_ats(session, board, timeout))
                    records.extend(board_records)
                    health.append(
                        SourceHealth(
                            source_id=board["id"],
                            status="ok" if board_records else "zero_results",
                            record_count=len(board_records),
                            latency_ms=int((time.perf_counter() - board_started) * 1000),
                        ).to_dict()
                    )
                except Exception as exc:
                    health.append(
                        SourceHealth(
                            source_id=board["id"],
                            status="failed",
                            record_count=0,
                            latency_ms=int((time.perf_counter() - board_started) * 1000),
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:300],
                            human_action="Drop the board if its public API contract changed.",
                        ).to_dict()
                    )
                time.sleep(interval)
        except Exception as exc:
            health.append(
                SourceHealth(
                    source_id=f"ats_harvest_page:{urlsplit(page_url).netloc}",
                    status="failed",
                    record_count=0,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:300],
                    human_action="Review public access; do not bypass.",
                ).to_dict()
            )
        time.sleep(interval)
    return records, health


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
                url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
                response = _request(session, url, timeout)
                records = _rise_sheet(response.text, {**source, "url": url})
            elif source["adapter"] == "ftb":
                records = _fetch_ftb_paginated(session, source, timeout)
            elif source["adapter"] == "wwr":
                response = _request(session, source["url"], timeout)
                records = _wwr(response.content, source)
            elif source["adapter"] == "teamtailor_ats":
                # Same reviewed-host gate every other ATS adapter goes through.
                # Without it the _ATS_HOSTS["teamtailor"] entry is decorative
                # and any board_url dropped into watchlist.yml is fetched
                # unchecked, over any scheme.
                response = _request(session, _verified_ats_url(source), timeout)
                records = _teamtailor(response.content, source)
            elif source["adapter"] == "yc":
                response = _request(session, source["url"], timeout)
                records = _yc(response.text, source)
            elif source["adapter"] == "wellfound":
                response = _request(session, source["url"], timeout)
                records = _wellfound(response.text, source)
            elif source["adapter"] in {"greenhouse_ats", "lever_ats", "ashby_ats", "workable_ats"}:
                records = _fetch_ats(session, source, timeout)
            elif str(source["adapter"]).startswith("apify_"):
                from apify_sources import fetch_apify_actor

                records, apify_metadata = fetch_apify_actor(source, config.get("apify", {}), timeout)
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
            error_type, action = (
                classify_http_failure(status_code)
                if status_code
                else (
                    type(exc).__name__,
                    "Inspect logs and the dated public source contract.",
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
    harvested, harvest_health = fetch_harvested_boards(
        session,
        config.get("ats_harvest", {}),
        timeout,
        float(config.get("min_interval_seconds", 2)),
    )
    all_records.extend(harvested)
    health.extend(harvest_health)
    return all_records, health


SPOTTED_SOURCE_ID = "human_spotted"
SPOTTED_FILE = "linkedin-leads.txt"


def load_spotted_leads(path: Path) -> list[Record]:
    """Daksh's own finds: one URL per line, `#` comments and blanks ignored.

    The pipeline may not open LinkedIn links, so these stay human tasks with
    provenance: tracked, deduplicated across runs, and surfaced in the digest.
    They can never become eligible on a bare URL alone.
    """
    from models import stable_id

    output: list[Record] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        url = clean_text(line)
        if not url or url.startswith("#"):
            continue
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            continue
        url = parts.geturl()
        if url in seen:
            continue
        seen.add(url)
        output.append(
            {
                "_source_id": SPOTTED_SOURCE_ID,
                "_source_url": url,
                "source": SPOTTED_SOURCE_ID,
                "id": stable_id("spotted", url, prefix="spotted"),
                "company": "",
                "title": "",
                "description": "",
                "location": "",
                "link": url,
                "source_url": url,
                "apply_url": url,
                "posted_at": "",
                "source_confidence": "low",
                "verification_status": "human_spotted_unverified",
                "source_priority": 1,
            }
        )
    return output


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
