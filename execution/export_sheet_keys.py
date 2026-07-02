"""
export_sheet_keys.py
---------------------
Pre-run step: exports existing Google Sheet dedup keys to .tmp/existing_sheet_keys.json
so the scraper can skip already-known internships before fetching.

Output:
    .tmp/existing_sheet_keys.json  - list of URL keys and "company:role" keys
"""

import json
import logging
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

TMP_DIR = ".tmp"
OUTPUT_FILE = os.path.join(TMP_DIR, "existing_sheet_keys.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _normalize_company(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r'\b(inc\.?|pvt\.?|ltd\.?|llp|llc|corp\.?|limited|private|technologies|tech|solutions|services|group|global|india)\b', '', n)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n


def _std_role_key(role: str) -> str:
    r = role.lower()
    for cat, kws in [
        ("software",  ["software", "sde", "developer", "frontend", "backend", "full stack", "web", "ios", "android"]),
        ("data",      ["data", "machine learning", "ml", "ai", "analytics", "scientist"]),
        ("product",   ["product", "apm"]),
        ("marketing", ["marketing", "seo", "social media", "content"]),
        ("design",    ["design", "ui", "ux", "graphic", "video", "animation"]),
        ("finance",   ["finance", "audit", "accounting", "ca "]),
        ("sales",     ["sales", "business development", "bd"]),
        ("hr",        ["hr", "human resources", "talent", "recruitment"]),
        ("strategy",  ["founder", "generalist", "chief of staff", "operations", "strategy"]),
        ("legal",     ["law", "legal", "compliance"]),
        ("research",  ["research"]),
    ]:
        if any(k in r for k in kws):
            return cat
    return r[:20]


def main():
    os.makedirs(TMP_DIR, exist_ok=True)

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        logger.warning("GOOGLE_SHEET_ID not set — writing empty key file")
        with open(OUTPUT_FILE, "w") as f:
            json.dump([], f)
        return

    try:
        # Reuse auth from publish_to_sheets
        try:
            from execution.publish_to_sheets import get_sheets_service
        except ImportError:
            from publish_to_sheets import get_sheets_service

        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="Sheet1!A:M"
        ).execute()

        values = result.get("values", [])
        keys = []

        for row in values[1:]:
            if not row:
                continue
            title = row[0].lower().strip() if row else ""
            company = row[10] if len(row) > 10 else ""
            url = row[12].strip() if len(row) > 12 and row[12] else ""

            if url:
                keys.append(url)
            if company and title:
                keys.append(f"{_normalize_company(company)}:{_std_role_key(title)}")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(keys, f)

        logger.info("Exported %d existing dedup keys → %s", len(keys), OUTPUT_FILE)

    except Exception as e:
        logger.warning("Could not export sheet keys (%s) — scraper will run without pre-filter", e)
        with open(OUTPUT_FILE, "w") as f:
            json.dump([], f)


if __name__ == "__main__":
    main()
