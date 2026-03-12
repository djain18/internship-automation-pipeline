"""
cleanup_expired.py
-------------------
Removes internship listings older than 4 days from Google Sheets.
Designed to run as the second daily run (10 PM) to ensure freshness.

Logic:
1. Read all rows from Google Sheet
2. Parse "Posted" or "Added On" column for date
3. Delete rows where date > 4 days ago
4. Log removed entries

Prerequisites:
    - credentials.json / token.json in project root
    - GOOGLE_SHEET_ID in .env
"""

import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Constants
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_AGE_DAYS = 4  # Maximum age before removal


def get_credentials():
    """Get or refresh Google OAuth credentials."""
    creds = None
    
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"Missing {CREDENTIALS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    
    return creds


def get_sheets_service():
    """Build Google Sheets API service."""
    creds = get_credentials()
    return build("sheets", "v4", credentials=creds)


def parse_date(date_str: str) -> datetime | None:
    """
    Parse various date formats from the sheet.
    Returns datetime or None if unparseable.
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try common formats
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%d %b %Y",
        "%Y-%m-%dT%H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Try relative time parsing (e.g., "2 hours ago", "3 days ago")
    relative_match = re.search(r"(\d+)\s*(hour|day|minute|week)s?\s*ago", date_str.lower())
    if relative_match:
        num = int(relative_match.group(1))
        unit = relative_match.group(2)
        
        now = datetime.now()
        if "hour" in unit:
            return now - timedelta(hours=num)
        elif "day" in unit:
            return now - timedelta(days=num)
        elif "minute" in unit:
            return now - timedelta(minutes=num)
        elif "week" in unit:
            return now - timedelta(weeks=num)
    
    return None


def cleanup_expired_listings():
    """
    Main cleanup function.
    Reads sheet, identifies expired rows, deletes them.
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("ERROR: GOOGLE_SHEET_ID not set in environment")
        return
    
    service = get_sheets_service()
    sheet = service.spreadsheets()
    
    # Read all data
    print("Reading sheet data...")
    result = sheet.values().get(
        spreadsheetId=sheet_id,
        range="Sheet1!A:Z"
    ).execute()
    
    values = result.get("values", [])
    if not values:
        print("Sheet is empty.")
        return
    
    # Find header row and identify date columns
    headers = values[0]
    
    # Look for "Posted" or "Added On" column
    posted_col_idx = None
    added_col_idx = None
    
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        if "posted" in h_lower:
            posted_col_idx = i
        if "added" in h_lower:
            added_col_idx = i
    
    date_col_idx = posted_col_idx if posted_col_idx is not None else added_col_idx
    
    if date_col_idx is None:
        print("WARNING: No 'Posted' or 'Added On' column found. Using row index as fallback.")
        # Fallback: Delete oldest rows if we can't determine date
        return
    
    print(f"Using column {date_col_idx} ('{headers[date_col_idx]}') for date check")
    
    # Identify rows to delete (1-indexed for Sheets API, skip header)
    now = datetime.now()
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    rows_to_delete = []
    
    for row_num, row in enumerate(values[1:], start=2):  # Start at 2 (after header)
        if len(row) <= date_col_idx:
            continue
        
        date_str = row[date_col_idx]
        parsed_date = parse_date(date_str)
        
        if parsed_date and parsed_date < cutoff:
            title = row[2] if len(row) > 2 else "Unknown"
            rows_to_delete.append({
                "row_num": row_num,
                "title": title,
                "date": date_str,
                "parsed": parsed_date.isoformat()
            })
    
    if not rows_to_delete:
        print(f"No expired listings found (all within {MAX_AGE_DAYS} days).")
        return
    
    print(f"Found {len(rows_to_delete)} expired listings to remove:")
    for r in rows_to_delete[:5]:  # Show first 5
        print(f"  - Row {r['row_num']}: {r['title']} ({r['date']})")
    
    # Delete rows (in reverse order to avoid index shifting)
    rows_to_delete.sort(key=lambda x: x["row_num"], reverse=True)
    
    requests = []
    for r in rows_to_delete:
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": 0,  # Assumes first sheet
                    "dimension": "ROWS",
                    "startIndex": r["row_num"] - 1,  # 0-indexed
                    "endIndex": r["row_num"]
                }
            }
        })
    
    # Execute batch delete
    if requests:
        print(f"Deleting {len(requests)} rows...")
        sheet.batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": requests}
        ).execute()
        print("Cleanup complete!")
    
    return len(rows_to_delete)


def main():
    print("=" * 50)
    print("INTERNSHIP EXPIRY CLEANUP")
    print(f"Removing listings older than {MAX_AGE_DAYS} days")
    print("=" * 50)
    
    try:
        deleted_count = cleanup_expired_listings()
        if deleted_count:
            print(f"\nSUCCESS: Removed {deleted_count} expired listings.")
        else:
            print("\nNo action needed - all listings are fresh.")
    except Exception as e:
        print(f"ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
