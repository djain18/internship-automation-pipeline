"""
publish_founders_roles.py
--------------------------
Publishes Daksh's personal Founder's Office / AI Automation / GTM job feed to
its own dedicated Google Sheet (separate from the RISE production sheet).
Reuses OAuth + dedup helpers from publish_to_sheets.py.

Sheet: "Daksh - Founder's Office / AI Automation / GTM Roles"
       https://docs.google.com/spreadsheets/d/1C-3LA0SIQMtHo13NqICAuY1T0GCZjsibczsg6Y76iEc
"""
import os
import sys
import json
import logging
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(__file__))
from publish_to_sheets import (
    get_sheets_service, _normalize_company, standardize_role_for_dedup, _with_retry,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

FOUNDERS_SHEET_ID = "1C-3LA0SIQMtHo13NqICAuY1T0GCZjsibczsg6Y76iEc"
TMP_DIR = ".tmp"
INPUT_FILE = os.path.join(TMP_DIR, "founders_roles_clean.json")

HEADERS = ["Title", "Type", "Timing", "Description", "Stipend/Salary", "Duration",
           "Experience", "Location", "Deadline", "Tags", "HiringOrganization",
           "HiringManager", "Post URL", "Apply Link", "Contact Email", "Date Added",
           "AI Relevance", "Role Track", "PostedDate"]


def generate_dedup_key(item):
    url = (item.get("url") or "").strip()
    if url:
        return url
    company = _normalize_company(item.get("company") or "")
    role = standardize_role_for_dedup(item.get("title") or item.get("role") or "")
    return f"{company}:{role}" if company and role else None


def fetch_existing_keys(service, sheet_id, sheet_name="Sheet1"):
    result = _with_retry(lambda: service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"{sheet_name}!A:S").execute())
    values = result.get("values", [])
    keys = set()
    for row in values[1:]:
        if not row:
            continue
        title = row[0] if len(row) > 0 else ""
        company = row[10] if len(row) > 10 else ""
        url = row[12].strip() if len(row) > 12 and row[12] else ""
        if url:
            keys.add(url)
        if company and title:
            keys.add(f"{_normalize_company(company)}:{standardize_role_for_dedup(title)}")
    return keys


def main():
    if not os.path.exists(INPUT_FILE):
        logger.warning("%s not found — nothing to publish.", INPUT_FILE)
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        items = json.load(f)
    if not items:
        logger.warning("No roles to publish.")
        return

    logger.info("Loaded %d roles from %s", len(items), INPUT_FILE)
    service = get_sheets_service()
    existing = fetch_existing_keys(service, FOUNDERS_SHEET_ID)
    logger.info("Found %d existing dedup keys in the sheet", len(existing))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows, seen_batch = [], set()
    for item in items:
        key = generate_dedup_key(item)
        if key and (key in existing or key in seen_batch):
            continue
        if key:
            seen_batch.add(key)

        tags = item.get("tags", [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        rows.append([
            item.get("title", ""), item.get("type", ""), item.get("timing", ""),
            item.get("description", ""), item.get("stipend", ""), item.get("duration", ""),
            item.get("experience", ""), item.get("location", ""), item.get("deadline", ""),
            tags_str, item.get("hiringOrganization", ""), item.get("author_name", ""),
            item.get("url", ""), item.get("apply_link", ""), item.get("contact_email", ""),
            timestamp, item.get("ai_relevance", ""), item.get("role_track", ""),
            item.get("posted_date", ""),
        ])

    if not rows:
        logger.info("No new roles to add (all duplicates).")
        print("Appended 0 new roles (all were already in the sheet).")
        return

    _with_retry(lambda: service.spreadsheets().values().append(
        spreadsheetId=FOUNDERS_SHEET_ID, range="Sheet1!A:S",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute())

    logger.info("Appended %d new roles", len(rows))
    print(f"Appended {len(rows)} new roles to https://docs.google.com/spreadsheets/d/{FOUNDERS_SHEET_ID}")


if __name__ == "__main__":
    main()
