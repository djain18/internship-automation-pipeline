"""
sheets.py
---------
Reads listings from Google Sheets.

Strategy: uses the Sheets API v4 with an API key (sheet must be
"Anyone with link can view"). Falls back to the local seed JSON
if the sheet is unreachable.

Sheet columns (A–S):
  Title, Type, Timing, Description, Stipend, Duration, Experience,
  Location, Deadline, Tags, HiringOrganization, HiringManager,
  Post URL, Apply Link, Contact Email, Date Added, Subchips, Similar Fields,
  PostedDate

A second worksheet named "Meta" holds the latest pipeline run metrics
(run_at, scanned, rejected, added) so /api/stats can report real numbers
instead of fabricated ones.
"""

from __future__ import annotations

import os
import re
import csv
import io
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env so GOOGLE_SHEET_ID is available in local dev.
load_dotenv()

log = logging.getLogger(__name__)

# Allow very large cells (long descriptions) when parsing the CSV export.
csv.field_size_limit(10_000_000)

SHEET_ID  = os.getenv("GOOGLE_SHEET_ID", "")
SHEET_GID = os.getenv("GOOGLE_SHEET_GID", "0")  # first tab by default
SHEET_NAME = "Sheet1"
SEED_FILE  = Path(__file__).parent / "seed_listings.json"


# ── column indices ────────────────────────────────────────────
COL = {
    "title":    0,
    "type":     1,
    "timing":   2,
    "desc":     3,
    "stipend":  4,
    "duration": 5,
    "exp":      6,
    "location": 7,
    "deadline": 8,
    "tags":     9,
    "org":      10,
    "manager":  11,
    "postUrl":  12,
    "applyLink":13,
    "contact":  14,
    "dateAdded":15,
    "subchips": 16,
    "similar":  17,
    "postedDate":18,
}


def _parse_stipend(raw: str) -> int:
    if not raw:
        return 0
    cleaned = str(raw).replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*([kKlL])\b", cleaned)
    if m:
        amt = float(m.group(1))
        return int(amt * 1000) if m.group(2).lower() == "k" else int(amt * 100_000)
    m = re.search(r"\d+", cleaned)
    return int(m.group()) if m else 0


def _hours_ago(date_str: str) -> int:
    if not date_str:
        return 24
    # NB: the pipeline writes "Date Added" as "%Y-%m-%d %H:%M" (no seconds), so
    # that format must be included or freshness silently defaults to 24h.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - dt
            return max(1, int(delta.total_seconds() / 3600))
        except ValueError:
            continue
    return 24


def _infer_cluster(title: str, tags: list[str]) -> str:
    text = (title + " " + " ".join(tags)).lower()
    if any(w in text for w in ["software", "sde", "developer", "frontend", "backend", "full stack", "web", "ios", "android", "flutter", "mobile"]): return "Software"
    if any(w in text for w in ["data", "machine learning", "ml", "ai", "analytics", "scientist"]): return "Data/AI"
    if any(w in text for w in ["product", " pm ", "apm"]): return "Product"
    if any(w in text for w in ["design", "ui", "ux", "graphic", "video", "motion", "figma"]): return "Design"
    if any(w in text for w in ["marketing", "seo", "social media", "growth", "performance"]): return "Marketing"
    if any(w in text for w in ["finance", "audit", "accounting", "equity", "markets"]): return "Finance"
    if any(w in text for w in ["sales", "business development", "bd", "bdr", "sdr"]): return "Business Dev"
    if any(w in text for w in ["hr", "human resources", "talent", "recruit"]): return "HR"
    if any(w in text for w in ["content", "writing", "copywriting", "editorial"]): return "Content"
    if any(w in text for w in ["legal", "compliance", "contracts", "law"]): return "Legal"
    return "Operations"


def _score(hours_ago: int, stipend: int) -> int:
    freshness = max(0, 100 - hours_ago * 3)
    stipend_score = min(40, int(stipend / 1500)) if stipend else 0
    return min(99, max(50, freshness // 2 + stipend_score + 50))


def _row_to_listing(row: list[str], idx: int) -> dict:
    def g(i): return row[i].strip() if len(row) > i else ""

    title    = g(COL["title"])
    org      = g(COL["org"])
    tags     = [t.strip() for t in g(COL["tags"]).split(",") if t.strip()]
    subchips = [s.strip() for s in g(COL["subchips"]).split(",") if s.strip()]
    similar  = [s.strip() for s in g(COL["similar"]).split(",") if s.strip()]
    stipend  = _parse_stipend(g(COL["stipend"]))
    # Freshness is based on when the internship was actually POSTED, falling
    # back to when the row was added if the pipeline couldn't resolve a date.
    hours    = _hours_ago(g(COL["postedDate"]) or g(COL["dateAdded"]))

    # stable ID: hash of org+title
    raw_id = hashlib.md5(f"{org}:{title}".encode()).hexdigest()[:8]

    return {
        "id":        f"sh-{raw_id}",
        "title":     title,
        "org":       org,
        "editor":    g(COL["manager"]),
        "cluster":   _infer_cluster(title, tags),
        "location":  g(COL["location"]),
        "type":      g(COL["type"]) or "Onsite",
        "timing":    g(COL["timing"]) or "Full-time",
        "stipend":   stipend,
        "duration":  g(COL["duration"]),
        "experience":g(COL["exp"]) or "Fresher",
        "deadline":  g(COL["deadline"]),
        "hoursAgo":  hours,
        "score":     _score(hours, stipend),
        "tags":      tags,
        "subchips":  subchips,
        "similar":   similar,
        "contact":   g(COL["contact"]),
        "applyLink": g(COL["applyLink"]),
        "postUrl":   g(COL["postUrl"]),
        "desc":      g(COL["desc"]) or f"{title} at {org}.",
    }


async def _fetch_from_sheets() -> list[dict]:
    """Read the sheet keyless via Google's CSV export.

    Requires only that the sheet be "anyone with the link can view" — no
    API key/secret. Returns listings parsed from the data rows (header skipped).
    """
    if not SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID not set")

    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
        f"?format=csv&gid={SHEET_GID}"
    )
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        text = resp.text

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []

    # Skip header row; keep rows that have a non-empty Title (col A).
    data_rows = [r for r in rows[1:] if r and r[0].strip()]
    listings = [_row_to_listing(row, i) for i, row in enumerate(data_rows)]
    # Sort freshest first
    return sorted(listings, key=lambda x: x["hoursAgo"])


async def fetch_listings() -> list[dict]:
    try:
        listings = await _fetch_from_sheets()
        log.info("Loaded %d listings from Google Sheets", len(listings))
        return listings
    except Exception as e:
        log.warning("Sheets fetch failed (%s), falling back to seed", e)
        if SEED_FILE.exists():
            with open(SEED_FILE) as f:
                return json.load(f)
        return []


async def _fetch_meta() -> dict | None:
    """Read the latest pipeline run metrics from the 'Meta' worksheet.

    Uses the gviz CSV endpoint, which addresses a tab by name (no gid needed).
    Returns None if the tab doesn't exist yet (e.g. before the first run that
    writes it), so callers can fall back gracefully.
    """
    if not SHEET_ID:
        return None
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet=Meta"
    )
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        text = resp.text
    # gviz returns an HTML error page (not CSV) when the tab is missing.
    if text.lstrip().startswith("<"):
        return None
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2 or not rows[1]:
        return None
    r = rows[1]

    def _int(i):
        try:
            return int(str(r[i]).strip())
        except (ValueError, IndexError):
            return 0

    return {
        "run_at":   r[0].strip() if r else "",
        "scanned":  _int(1),
        "rejected": _int(2),
        "added":    _int(3),
    }


async def fetch_stats() -> dict:
    """Real, measured stats — never fabricated.

    `verifiedToday` / `spikedToday` come from the pipeline's own run metrics
    (the Meta tab). If those aren't available yet, we degrade to what we can
    honestly derive from the live listings rather than inventing numbers.
    """
    listings = []
    try:
        listings = await _fetch_from_sheets()
    except Exception as e:
        log.warning("Stats: listings fetch failed (%s)", e)

    meta = None
    try:
        meta = await _fetch_meta()
    except Exception as e:
        log.info("Stats: no Meta tab yet (%s)", e)

    total = len(listings)
    return {
        "verifiedToday": meta["added"] if meta else total,
        "totalActive":   total,
        # Real count of posts the filters rejected on the last run; 0 (→ "—" in
        # the UI) when we haven't measured it rather than a fabricated number.
        "spikedToday":   meta["rejected"] if meta else 0,
        "scannedToday":  meta["scanned"] if meta else 0,
        # Every published listing passes the India-eligibility filter by
        # construction, so this is a true statement about the live set.
        "indiaEligible": total,
        "lastRun":       meta["run_at"] if meta else "",
    }
