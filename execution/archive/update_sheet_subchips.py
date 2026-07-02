"""
update_sheet_subchips.py
------------------------
Reads the existing Google Sheet and patches the Subchips (col Q) and
Similar Fields (col R) columns for every data row using field_clusters.py.

Usage:
    python execution/update_sheet_subchips.py [SHEET_ID]

If SHEET_ID is omitted, defaults to the nightly sheet from .env.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

try:
    from execution.field_clusters import get_subchips, get_similar_fields
    from execution.publish_to_sheets import get_credentials
except ImportError:
    from field_clusters import get_subchips, get_similar_fields
    from publish_to_sheets import get_credentials

from googleapiclient.discovery import build

SHEET_NAME = "Sheet1"
# Column indices (0-based): Q=16, R=17
SUBCHIPS_COL = 16
SIMILAR_COL   = 17

NIGHTLY_SHEET = os.getenv("GOOGLE_SHEET_ID", "1f6b_QgkmeOAu0XFpiYyDHMgfkXFKEsrX4gl8IjWbI1k")


def col_letter(idx: int) -> str:
    """Convert 0-based column index to A1 letter (e.g. 16 → Q)."""
    result = ""
    n = idx + 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def update_subchips(sheet_id: str):
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheets  = service.spreadsheets()

    # Read all data (columns A through R)
    range_read = f"{SHEET_NAME}!A:R"
    result = sheets.values().get(spreadsheetId=sheet_id, range=range_read).execute()
    rows = result.get("values", [])

    if not rows:
        print("No data found in sheet.")
        return

    header = rows[0]
    data_rows = rows[1:]  # skip header row
    print(f"Found {len(data_rows)} data rows.")

    updates = []
    matched = 0
    unmatched_titles = []

    for i, row in enumerate(data_rows):
        title = row[0].strip() if row else ""
        if not title:
            continue

        subchips     = get_subchips(title)
        similar      = get_similar_fields(title)
        row_number   = i + 2  # 1-based, row 1 is header

        if subchips:
            matched += 1
        else:
            unmatched_titles.append(title)

        updates.append({
            "range": f"{SHEET_NAME}!{col_letter(SUBCHIPS_COL)}{row_number}:{col_letter(SIMILAR_COL)}{row_number}",
            "values": [[subchips, similar]],
        })

    if not updates:
        print("Nothing to update.")
        return

    body = {"valueInputOption": "USER_ENTERED", "data": updates}
    sheets.values().batchUpdate(spreadsheetId=sheet_id, body=body).execute()

    print(f"\n✅ Updated {len(updates)} rows.")
    print(f"   Matched:   {matched}")
    print(f"   Unmatched: {len(unmatched_titles)}")
    if unmatched_titles:
        print("\nTitles with no cluster match:")
        for t in unmatched_titles:
            print(f"  - {t}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else NIGHTLY_SHEET
    print(f"Updating sheet: {target}")
    update_subchips(target)
