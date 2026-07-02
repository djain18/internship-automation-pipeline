"""
publish_to_sheets.py
---------------------
Publishes ranked internships to Google Sheets with idempotent update logic.

Input:
    .tmp/final_ranked_internships.json

Output:
    Google Sheet (configured via GOOGLE_SHEET_ID in .env)

Prerequisites:
    - credentials.json in project root
    - GOOGLE_SHEET_ID in .env
"""

import logging
import os
import json
import hashlib
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from execution.field_clusters import get_subchips, get_similar_fields
except ImportError:
    from field_clusters import get_subchips, get_similar_fields

# Load environment variables
load_dotenv()

# Constants
TMP_DIR = ".tmp"
INPUT_FILE = os.path.join(TMP_DIR, "final_ranked_internships.json")
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

import sys

# Google Sheets API scope
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Sheet headers (19 columns: A-S)
HEADERS = ["Title", "Type", "Timing", "Description", "Stipend", "Duration", "Experience", "Location", "Deadline", "Tags", "HiringOrganization", "HiringManager", "Post URL", "Apply Link", "Contact Email", "Date Added", "Subchips", "Similar Fields", "PostedDate"]

# Stale threshold: entries older than this many days are removed from the sheet
STALE_DAYS = 15

import re as _re


def _with_retry(fn, max_attempts=3, backoff=2):
    """Call fn(), retrying up to max_attempts times with exponential backoff."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                wait = backoff ** attempt
                logger.warning("Attempt %d/%d failed (%s). Retrying in %ds...", attempt + 1, max_attempts, exc, wait)
                time.sleep(wait)
    raise last_exc


def _parse_stipend_int(stipend: str):
    """Parse stipend to int, handling K (×1,000) and L (×1,00,000) suffixes.

    Examples: '10k' → 10000 | '10K' → 10000 | '5L' → 500000 | '10L' → 1000000
              '15000' → 15000 | '₹5,000/month' → 5000 | 'competitive' → ''
    """
    if not stipend:
        return ""
    cleaned = str(stipend).replace(",", "").strip()
    match = _re.search(r"(\d+(?:\.\d+)?)\s*([kKlL])\b", cleaned)
    if match:
        amount = float(match.group(1))
        return int(amount * 1000) if match.group(2).lower() == "k" else int(amount * 100000)
    match = _re.search(r"\d+", cleaned)
    return int(match.group()) if match else ""


def get_credentials():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        can_be_interactive = sys.stdin.isatty() and os.getenv("MODAL_RUN") != "1"

        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Token expired, attempting to refresh...")
                creds.refresh(Request())
            except Exception as e:
                logger.warning("Failed to refresh Google OAuth token: %s", e)
                if not can_be_interactive:
                    logger.error("Headless environment cannot perform interactive login. "
                                 "Run locally once to generate a fresh token.")
                    sys.exit(1)
                else:
                    logger.info("Falling back to interactive browser login...")
                    creds = None

        if not creds or not creds.valid:
            if not can_be_interactive and not os.path.exists(TOKEN_FILE):
                logger.error("Headless environment detected and token.json is missing. "
                             "Run locally first to generate token.json, or provide it via secrets.")
                sys.exit(1)

            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_FILE}. Download from Google Cloud Console."
                )

            logger.info("Starting interactive OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def get_sheets_service():
    """
    Build Google Sheets API service.
    """
    creds = get_credentials()
    return build("sheets", "v4", credentials=creds)

def _normalize_company(name: str) -> str:
    """Normalize company name for deduplication — strips suffixes and spaces."""
    n = name.lower().strip()
    n = _re.sub(r'\b(inc\.?|pvt\.?|ltd\.?|llp|llc|corp\.?|limited|private|technologies|tech|solutions|services|group|global|india)\b', '', n)
    n = _re.sub(r'[^a-z0-9]', '', n)
    return n


def standardize_role_for_dedup(role: str) -> str:
    """Map arbitrary job titles to strict generic categories for robust deduplication."""
    r = role.lower()
    if any(x in r for x in ['software', 'sde', 'developer', 'frontend', 'backend', 'full stack', 'app', 'web', 'ios', 'android']): return 'software'
    if any(x in r for x in ['data', 'machine learning', 'ml', 'ai', 'analytics', 'scientist']): return 'data'
    if any(x in r for x in ['product', 'pm']): return 'product'
    if any(x in r for x in ['marketing', 'seo', 'social media', 'content']): return 'marketing'
    if any(x in r for x in ['design', 'ui', 'ux', 'graphic', 'video', 'animation']): return 'design'
    if any(x in r for x in ['finance', 'audit', 'accounting', 'ca ']): return 'finance'
    if any(x in r for x in ['sales', 'business development', 'bd', 'bdr']): return 'sales'
    if any(x in r for x in ['hr', 'human resources', 'talent', 'recruitment']): return 'hr'
    return ''.join(filter(str.isalpha, r))

def generate_dedup_keys(item: dict) -> list:
    """
    Generate deduplication keys:
    1. The specific URL (to prevent same post twice)
    2. Company + Role (to prevent different recruiters posting exact same internship)
    Returns a list of keys so we can check if *any* exist.
    """
    keys = []
    
    url = item.get("url", "").strip()
    if url:
        keys.append(url)
        
    company = (item.get("company") or item.get("hiringOrganization") or "")
    role = (item.get("title") or item.get("role") or "").lower().strip()

    norm_company = _normalize_company(company)
    std_role = standardize_role_for_dedup(role)

    if norm_company and std_role:
        keys.append(f"{norm_company}:{std_role}")
        
    if not keys:
        keys.append(hashlib.md5(f"{company}:{role}".encode()).hexdigest())
        
    return keys


def fetch_existing_urls(service, sheet_id: str, sheet_name: str = "Sheet1") -> set:
    try:
        result = _with_retry(lambda: service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A:M"
        ).execute())

        values = result.get("values", [])
        keys = set()
        for row in values[1:]:
            if row:
                title = row[0].lower().strip() if row else ""
                company = row[10] if len(row) > 10 else ""
                url = row[12].strip() if len(row) > 12 and row[12] else ""
                if url:
                    keys.add(url)
                if company and title:
                    keys.add(f"{_normalize_company(company)}:{standardize_role_for_dedup(title)}")
        return keys

    except HttpError as e:
        if e.resp.status == 404:
            logger.info("Sheet not found, will create headers")
            return set()
        raise


def ensure_headers(service, sheet_id: str, sheet_name: str = "Sheet1"):
    try:
        result = _with_retry(lambda: service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1:R1"
        ).execute())
        values = result.get("values", [])
        if not values or values[0] != HEADERS:
            _with_retry(lambda: service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A1:S1",
                valueInputOption="RAW",
                body={"values": [HEADERS]}
            ).execute())
            logger.info("Headers set")
    except HttpError:
        _with_retry(lambda: service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1:R1",
            valueInputOption="RAW",
            body={"values": [HEADERS]}
        ).execute())
        logger.info("Headers created")


def append_new_entries(service, sheet_id: str, items: list, existing_urls: set, sheet_name: str = "Sheet1"):
    """
    Append new entries that don't exist in the sheet.
    Returns (count, new_items) where new_items are the items actually appended.
    """
    new_rows = []
    new_items = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    seen_in_batch = set()

    for rank, item in enumerate(items, 1):
        dedup_keys = generate_dedup_keys(item)

        # Skip if any of the keys already exists either in Sheet or previously in this batch
        if any(k in existing_urls or k in seen_in_batch for k in dedup_keys):
            continue

        for k in dedup_keys:
            seen_in_batch.add(k)
        new_items.append(item)
        
        tags_val = item.get("tags", [])
        tags_str = ", ".join(tags_val) if isinstance(tags_val, list) else str(tags_val)
        
        # Deadline: only show a real, extracted deadline. Never fabricate one —
        # a made-up date causes students to mis-judge urgency or miss real cutoffs.
        deadline = (item.get("deadline", "") or "").strip()
        if deadline.lower() == "null":
            deadline = ""

        row = [
            item.get("title", ""),
            item.get("type", ""),
            item.get("timing", ""),
            item.get("description", ""),
            _parse_stipend_int(item.get("stipend", "")),
            item.get("duration", ""),
            item.get("experience", ""),
            item.get("location", ""),
            deadline,
            tags_str,
            item.get("hiringOrganization", ""),
            item.get("author_name", ""),  # HiringManager
            item.get("url", ""),
            item.get("apply_link", ""),
            item.get("contact_email", ""),
            timestamp,                                        # Date Added (column P)
            get_subchips(item.get("title", "")),             # Subchips (column Q)
            get_similar_fields(item.get("title", "")),       # Similar Fields (column R)
            item.get("posted_date", ""),                     # PostedDate (column S)
        ]
        new_rows.append(row)
    
    if not new_rows:
        logger.info("No new entries to add")
        return 0, []

    response = _with_retry(lambda: service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A:S",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows}
    ).execute())

    logger.info("Appended %d new entries", len(new_rows))

    updates = response.get("updates", {})
    updated_range = updates.get("updatedRange")

    if updated_range:
        try:
            range_part = updated_range.split("!")[1]
            start_row = int("".join(filter(str.isdigit, range_part.split(":")[0])))
            end_row = int("".join(filter(str.isdigit, range_part.split(":")[1])))

            _with_retry(lambda: service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [{
                    "repeatCell": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": start_row - 1,
                            "endRowIndex": end_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": 19
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                                "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                "textFormat": {
                                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}
                                }
                            }
                        },
                        "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.foregroundColor"
                    }
                }]}
            ).execute())
            logger.info("Applied formatting to new rows")
        except Exception as e:
            logger.warning("Failed to format rows: %s", e)

    return len(new_rows), new_items


def remove_stale_entries(service, sheet_id: str, sheet_name: str = "Sheet1"):
    logger.info("Checking for stale entries (>%d days old)...", STALE_DAYS)
    
    try:
        result = _with_retry(lambda: service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A:S"
        ).execute())

        values = result.get("values", [])
        if len(values) <= 1:
            logger.info("No data rows to check")
            return 0

        data_rows = values[1:]
        cutoff = datetime.now() - timedelta(days=STALE_DAYS)

        rows_to_keep = []
        removed_count = 0

        for row in data_rows:
            date_added = row[15].strip() if len(row) > 15 and row[15] else ""
            if not date_added:
                rows_to_keep.append(row)
                continue
            try:
                if datetime.strptime(date_added[:10], "%Y-%m-%d") < cutoff:
                    removed_count += 1
                    continue
            except ValueError:
                pass
            rows_to_keep.append(row)

        if removed_count == 0:
            logger.info("No stale entries found")
            return 0

        _with_retry(lambda: service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A2:S{len(data_rows) + 1}"
        ).execute())

        if rows_to_keep:
            _with_retry(lambda: service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A2:S{len(rows_to_keep) + 1}",
                valueInputOption="RAW",
                body={"values": rows_to_keep}
            ).execute())

        logger.info("Removed %d stale entries from Google Sheet", removed_count)
        return removed_count

    except HttpError as e:
        logger.error("Error checking stale entries: %s", e)
        return 0


def write_run_metrics(service, sheet_id: str, added: int):
    """Persist real run metrics to a 'Meta' worksheet so the website's
    /api/stats can show measured numbers instead of fabricated ones.

    Reads scanned/rejected counts left behind by the scraper in
    .tmp/scrape_metrics.json (same machine, same run).
    """
    scanned = rejected = 0
    metrics_file = os.path.join(TMP_DIR, "scrape_metrics.json")
    if os.path.exists(metrics_file):
        try:
            with open(metrics_file) as f:
                m = json.load(f)
            scanned = int(m.get("scanned", 0))
            rejected = int(m.get("rejected", 0))
        except Exception as e:
            logger.warning("Could not read scrape metrics: %s", e)

    run_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = ["run_at", "scanned", "rejected", "added"]
    values = [header, [run_at, scanned, rejected, added]]

    try:
        # Create the Meta tab if it doesn't exist yet.
        try:
            _with_retry(lambda: service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": "Meta"}}}]},
            ).execute())
            logger.info("Created Meta worksheet")
        except HttpError as e:
            if "already exists" not in str(e):
                raise

        _with_retry(lambda: service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Meta!A1:D2",
            valueInputOption="RAW",
            body={"values": values},
        ).execute())
        logger.info("Wrote run metrics → Meta tab (scanned=%d rejected=%d added=%d)",
                    scanned, rejected, added)
    except Exception as e:
        logger.warning("Failed to write run metrics: %s", e)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Publishing to Google Sheets")

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise EnvironmentError("GOOGLE_SHEET_ID not set in .env")

    if not os.path.exists(INPUT_FILE):
        logger.warning("%s not found. Nothing to publish.", INPUT_FILE)
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        logger.warning("No internships to publish")
        return

    logger.info("Loaded %d internships from %s", len(items), INPUT_FILE)

    service = get_sheets_service()
    logger.info("Connected to Google Sheets API")

    ensure_headers(service, sheet_id)
    existing_urls = fetch_existing_urls(service, sheet_id)
    logger.info("Found %d existing dedup keys", len(existing_urls))

    appended_count, new_items = append_new_entries(service, sheet_id, items, existing_urls)
    remove_stale_entries(service, sheet_id)
    write_run_metrics(service, sheet_id, appended_count)

    # Write result so run_pipeline.py can check if target was met
    result_file = os.path.join(TMP_DIR, "publish_result.json")
    with open(result_file, "w") as f:
        json.dump({"appended": appended_count}, f)
    logger.info("Publish result: %d new entries → %s", appended_count, result_file)

    print(f"Sheet URL: https://docs.google.com/spreadsheets/d/{sheet_id}")
    # Rise is decoupled from the external ftbhustle API. The Google Sheet above is
    # the single source of truth — the Rise website's api/ reads directly from it.


if __name__ == "__main__":
    main()
