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

import os
import json
import hashlib
import requests
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
TMP_DIR = ".tmp"
INPUT_FILE = os.path.join(TMP_DIR, "final_ranked_internships.json")
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

import sys

# Google Sheets API scope
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Sheet headers (16 columns: A-P)
HEADERS = ["Title", "Type", "Timing", "Description", "Stipend", "Duration", "Experience", "Location", "Deadline", "Tags", "HiringOrganization", "HiringManager", "Post URL", "Apply Link", "Contact Email", "Date Added"]

# Stale threshold: entries older than this many days are removed from the sheet
STALE_DAYS = 4


def get_credentials():
    """
    Get or refresh Google OAuth credentials.
    """
    creds = None
    
    # Load existing token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # HEADLESS CHECK: Prevent interactive prompt on Modal/Cloud
            can_be_interactive = sys.stdin.isatty() and os.getenv("MODAL_RUN") != "1"
            
            if not can_be_interactive and not os.path.exists(TOKEN_FILE):
                print("\n❌ ERROR: Headless environment detected and token.json is missing.")
                print("   Run this script locally first to generate token.json, or provide it via secrets.")
                sys.exit(1)

            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_FILE}. Download from Google Cloud Console."
                )
            
            print("🔑 Starting interactive OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save token for next run
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    
    return creds


def get_sheets_service():
    """
    Build Google Sheets API service.
    """
    creds = get_credentials()
    return build("sheets", "v4", credentials=creds)


def generate_dedup_key(item: dict) -> str:
    """
    Generate deduplication key from URL or company+title hash.
    """
    url = item.get("url", "").strip()
    if url:
        return url
    
    # Fallback: hash of company + title
    company = item.get("company", "").lower().strip()
    title = item.get("title", "").lower().strip()
    combined = f"{company}:{title}"
    return hashlib.md5(combined.encode()).hexdigest()


def fetch_existing_urls(service, sheet_id: str, sheet_name: str = "Sheet1") -> set:
    """
    Fetch existing Post URLs from column M (index 12).
    """
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!M:M"
        ).execute()
        
        values = result.get("values", [])
        # Skip header row, get URLs
        urls = set()
        for row in values[1:]:  # Skip header
            if row:
                urls.add(row[0].strip())
        
        return urls
    
    except HttpError as e:
        if e.resp.status == 404:
            print("Sheet not found, will create headers")
            return set()
        raise


def ensure_headers(service, sheet_id: str, sheet_name: str = "Sheet1"):
    """
    Ensure headers exist in the first row.
    """
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1:P1"
        ).execute()
        
        values = result.get("values", [])
        if not values or values[0] != HEADERS:
            # Set headers
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A1:P1",
                valueInputOption="RAW",
                body={"values": [HEADERS]}
            ).execute()
            print("Headers set")
    
    except HttpError:
        # Create headers
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1:P1",
            valueInputOption="RAW",
            body={"values": [HEADERS]}
        ).execute()
        print("Headers created")


def append_new_entries(service, sheet_id: str, items: list, existing_urls: set, sheet_name: str = "Sheet1"):
    """
    Append new entries that don't exist in the sheet.
    """
    new_rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    for rank, item in enumerate(items, 1):
        dedup_key = generate_dedup_key(item)
        
        # Skip if already exists
        if dedup_key in existing_urls:
            continue
        
        tags_val = item.get("tags", [])
        tags_str = ", ".join(tags_val) if isinstance(tags_val, list) else str(tags_val)
        
        row = [
            item.get("title", ""),
            item.get("type", ""),
            item.get("timing", ""),
            item.get("description", ""),
            item.get("stipend", ""),
            item.get("duration", ""),
            item.get("experience", ""),
            item.get("location", "Not specified"),
            item.get("deadline", ""),
            tags_str,
            item.get("hiringOrganization", ""),
            item.get("author_name", ""),  # HiringManager
            item.get("url", ""),
            item.get("apply_link", ""),
            item.get("contact_email", ""),
            timestamp,  # Date Added (column P)
        ]
        new_rows.append(row)
    
    if not new_rows:
        print("No new entries to add")
        return 0
    
    # Append rows
    response = service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A:P",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows}
    ).execute()
    
    print(f"Appended {len(new_rows)} new entries")
    
    # Highlight new rows if added
    updates = response.get("updates", {})
    updated_range = updates.get("updatedRange")
    
    if updated_range:
        try:
            # Parse range to get start/end row
            # Format: Sheet1!A10:I15
            range_part = updated_range.split("!")[1]
            start_row_part = range_part.split(":")[0]
            start_row = int("".join(filter(str.isdigit, start_row_part)))
            end_row_part = range_part.split(":")[1]
            end_row = int("".join(filter(str.isdigit, end_row_part)))
            
            # Google Sheets API is 0-indexed for startRowIndex, but row numbers are 1-indexed
            # start_row is 1-indexed from the range string
            
            # Apply light green background
            requests = [{
                "repeatCell": {
                    "range": {
                        "sheetId": 0,  # Assuming first sheet (GID 0). TODO: Get actual sheetId
                        "startRowIndex": start_row - 1,
                        "endRowIndex": end_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": 14
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {
                                "red": 0.85,
                                "green": 0.93,
                                "blue": 0.83
                            }
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }]
            
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests}
            ).execute()
            print("Highlighted new rows")
            
        except Exception as e:
            print(f"Failed to highlight rows: {e}")

    return len(new_rows)


def update_ranks(service, sheet_id: str, sheet_name: str = "Sheet1"):
    """
    Update rank column based on score (re-rank all entries).
    """
    try:
        # Get all data
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A:I"
        ).execute()
        
        values = result.get("values", [])
        if len(values) <= 1:
            return  # No data rows
        
        # Keep header, sort rest by score descending
        header = values[0]
        data_rows = values[1:]
        
        # Sort by score (column B, index 1)
        def get_score(row):
            try:
                return int(row[1]) if len(row) > 1 else 0
            except (ValueError, TypeError):
                return 0
        
        data_rows.sort(key=get_score, reverse=True)
        
        # Update ranks
        for i, row in enumerate(data_rows, 1):
            if row:
                row[0] = i  # Update rank
        
        # Write back
        all_rows = [header] + data_rows
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1:I{len(all_rows)}",
            valueInputOption="RAW",
            body={"values": all_rows}
        ).execute()
        
        print("Ranks updated")
    
    except HttpError as e:
        print(f"Error updating ranks: {e}")


def ingest_to_api(items: list):
    """
    Push extracted internships to the internal FTB Hustle API.
    """
    print("="*60)
    print("Pushing to FTB Hustle API")
    print("="*60)
    
    url = "https://internal.ftbhustle.com/api/internships/ingest"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer 510d82ca926c7cbd49bab2afae3d00a7c6a15f7a5029e02ea6987ec7f4785068"
    }
    
    payload = []
    for item in items:
        # Map item to API schema
        
        # Tags needs to be a list for the API
        tags_val = item.get("tags", [])
        if isinstance(tags_val, str):
            tags_val = [t.strip() for t in tags_val.split(",") if t.strip()]
            
        # Parse timing based on API requirements (expecting full_time, part_time)
        timing_val = item.get("timing", "").lower().replace("-", "_")
        if "full" in timing_val: timing_val = "full_time"
        elif "part" in timing_val: timing_val = "part_time"
        
        # Parse type based on API requirements
        type_val = item.get("type", "").lower()
        if "remote" in type_val: type_val = "remote"
        elif "hybrid" in type_val: type_val = "hybrid"
        elif "onsite" in type_val: type_val = "onsite"
        
        deadline = item.get("deadline", "")
        # The API schema expects YYYY-MM-DD or similar. For now passing what LLM gives us.
        
        entry = {
            "title": item.get("title") or item.get("role") or "Internship",
            "hiringOrganization": item.get("hiringOrganization") or item.get("company", "Unknown"),
            "link": item.get("apply_link") or item.get("url") or "",
            "description": item.get("description") or item.get("post_text", ""),
            "type": type_val,
            "timing": timing_val,
            "stipend": item.get("stipend") or "",
            "duration": item.get("duration") or "",
            "experience": item.get("experience") or "",
            "location": item.get("location", "Not specified"),
            "deadline": deadline,
            "tags": tags_val,
            "hiringManager": item.get("author_name", ""), # Best effort approximation
            "isVerified": False,  # Default to false for human review if needed
            "isActive": True,
            "rawText": item.get("description") or item.get("post_text", "")
        }
        payload.append(entry)
        
    if not payload:
        print("No items to ingest.")
        return
        
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            print(f"Successfully ingested {len(payload)} internships to API!")
        else:
            print(f"Failed to ingest to API. Status: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"API Request Exception: {str(e)}")


def remove_stale_entries(service, sheet_id: str, sheet_name: str = "Sheet1"):
    """
    Remove entries from the Google Sheet that are older than STALE_DAYS.
    Only removes from the sheet — does NOT touch the FTB API.
    
    Uses column P ("Date Added") to determine age.
    """
    print(f"\nChecking for stale entries (>{STALE_DAYS} days old)...")
    
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A:P"
        ).execute()
        
        values = result.get("values", [])
        if len(values) <= 1:
            print("No data rows to check")
            return 0
        
        header = values[0]
        data_rows = values[1:]
        cutoff = datetime.now() - timedelta(days=STALE_DAYS)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        
        rows_to_keep = []
        removed_count = 0
        
        for row in data_rows:
            # Column P (index 15) is "Date Added"
            date_added = row[15].strip() if len(row) > 15 and row[15] else ""
            
            if not date_added:
                # No date — keep it (legacy row)
                rows_to_keep.append(row)
                continue
            
            # Parse date (format: "YYYY-MM-DD HH:MM")
            try:
                row_date = datetime.strptime(date_added[:10], "%Y-%m-%d")
                if row_date < cutoff:
                    removed_count += 1
                    continue  # Skip (remove) this row
            except ValueError:
                pass  # Can't parse — keep it
            
            rows_to_keep.append(row)
        
        if removed_count == 0:
            print("No stale entries found")
            return 0
        
        # Clear all data rows and rewrite with kept rows
        # First clear the entire data range
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A2:P{len(data_rows) + 1}"
        ).execute()
        
        # Then write back the kept rows
        if rows_to_keep:
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A2:P{len(rows_to_keep) + 1}",
                valueInputOption="RAW",
                body={"values": rows_to_keep}
            ).execute()
        
        print(f"Removed {removed_count} stale entries from Google Sheet")
        return removed_count
    
    except HttpError as e:
        print(f"Error checking stale entries: {e}")
        return 0


def main():
    """
    Main execution flow:
    1. Load ranked internships
    2. Connect to Google Sheets
    3. Fetch existing entries
    4. Append new entries (with Date Added timestamp)
    5. Remove stale entries from sheet (>4 days old)
    6. Push new entries to FTB Hustle API
    """
    print("="*60)
    print("Publishing to Google Sheets")
    print("="*60)
    
    # Check sheet ID
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise EnvironmentError("GOOGLE_SHEET_ID not set in .env")
    
    # Load input data
    if not os.path.exists(INPUT_FILE):
        print(f"Warning: {INPUT_FILE} not found. Nothing to publish.")
        return
    
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)
    
    if not items:
        print("Warning: No internships to publish")
        return
    
    print(f"Loaded {len(items)} internships from {INPUT_FILE}")
    
    # Connect to Google Sheets
    service = get_sheets_service()
    print("Connected to Google Sheets API")
    
    # Ensure headers
    ensure_headers(service, sheet_id)
    
    # Fetch existing URLs for dedup
    existing_urls = fetch_existing_urls(service, sheet_id)
    print(f"Found {len(existing_urls)} existing entries")
    
    # Append new entries (skips duplicates automatically)
    added = append_new_entries(service, sheet_id, items, existing_urls)
    
    # Remove stale entries from sheet only (not from API)
    removed = remove_stale_entries(service, sheet_id)
    
    print(f"\nSheet URL: https://docs.google.com/spreadsheets/d/{sheet_id}")
    print("Done with Google Sheets!")
    
    # Push to internal FTB Hustle API (only new items, dedup handled by API)
    ingest_to_api(items)


if __name__ == "__main__":
    main()
