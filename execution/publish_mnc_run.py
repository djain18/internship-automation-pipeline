"""
publish_mnc_run.py
---------------------
Publishes MNC Run results to Google Sheets.
Input: .tmp/mnc_run_clean.json
Output: Google Sheet (configured via GOOGLE_SHEET_ID)
"""

import os
import json
import re
import hashlib
import sys
from datetime import datetime
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

# Constants
TMP_DIR = ".tmp"
INPUT_FILE = os.path.join(TMP_DIR, "mnc_run_clean.json")
if len(sys.argv) > 1:
    INPUT_FILE = sys.argv[1]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = ["Rank", "Score", "Title", "Role", "Company", "Location", "Source", "URL", "Posted", "Added On", "Poster Type", "Apply Link", "Work Type"]

def clean_company_name(name):
    """Strip URL artifacts from company names. e.g. 'www.zepto.com' -> 'Zepto'"""
    if not name:
        return name
    # Remove protocol
    name = re.sub(r'https?://', '', name)
    # Remove www.
    name = re.sub(r'^www\.', '', name)
    # Remove trailing paths
    name = name.split('/')[0]
    # Remove common TLDs
    name = re.sub(r'\.(com|in|io|org|co|net|ai|dev|xyz|tech|app)$', '', name, flags=re.IGNORECASE)
    # Remove subdomains like careers.zepto -> zepto
    if '.' in name:
        name = name.split('.')[-1]
    # Title case and strip
    name = name.strip().title()
    return name

def get_credentials():
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
    creds = get_credentials()
    return build("sheets", "v4", credentials=creds)

def generate_dedup_key(item):
    url = item.get("url", "").strip()
    role = item.get("role", "").strip().lower()
    # Dedup by URL+Role so same post with different roles creates separate rows
    if url:
        return f"{url}|{role}"
    return hashlib.md5((item.get("post_text", "")[:100] + role).encode()).hexdigest()

def fetch_existing_urls(service, sheet_id, sheet_name="Sheet1"):
    try:
        # Fetch URL (col H) and Role (col D) to build composite dedup keys
        result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"{sheet_name}!A1:M").execute()
        values = result.get("values", [])
        keys = set()
        for row in values[1:]:
            if len(row) >= 8:
                url = row[7].strip() if len(row) > 7 else ""
                role = row[3].strip().lower() if len(row) > 3 else ""
                if url:
                    keys.add(f"{url}|{role}")
        return keys
    except HttpError:
        return set()

def ensure_headers(service, sheet_id, sheet_name="Sheet1"):
    try:
        result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"{sheet_name}!A1:M1").execute()
        if not result.get("values"):
            service.spreadsheets().values().update(spreadsheetId=sheet_id, range=f"{sheet_name}!A1:M1", valueInputOption="RAW", body={"values": [HEADERS]}).execute()
    except HttpError:
        pass

def append_new_entries(service, sheet_id, items, existing_urls, sheet_name="Sheet1"):
    new_rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Get current max rank
    try:
        result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"{sheet_name}!A:A").execute()
        values = result.get("values", [])
        start_rank = len(values) # 1-indexed (header is 1)
    except:
        start_rank = 1

    for i, item in enumerate(items):
        dedup_key = generate_dedup_key(item)
        if dedup_key in existing_urls:
            continue
        
        company = str(item.get("company", "") or "").strip()
        if not company or company.lower() in ["unknown", "not specified", "not mentioned", "n/a", "unknown (whatsapp)", "notion entry"]:
            continue
        
        # Clean URL-style company names
        company = clean_company_name(company)
            
        row = [
            start_rank + i,
            str(item.get("engagement_score", 0)),
            str(item.get("author_headline", "") or ""),
            str(item.get("role", "Internship") or "Internship"),
            company,
            str(item.get("location", "Not specified") or "Not specified"),
            "LinkedIn Post (MNC Run)",
            str(item.get("url", "") or ""),
            str(item.get("posted_time", "") or ""),
            timestamp,
            str(item.get("author_type", "Unknown") or "Unknown"),
            str(item.get("apply_link", "") or ""),
            str(item.get("work_type", "") or "")
        ]
        new_rows.append(row)
    
    if not new_rows:
        print("No new entries to add")
        return 0
    
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A:M",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows}
    ).execute()
    print(f"Appended {len(new_rows)} new entries")
    return len(new_rows)

def main():
    print("Publishing MNC Run Results...")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not os.path.exists(INPUT_FILE):
        print("No output file found yet.")
        return
        
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)
        
    if not items:
        print("No items to publish.")
        return

    service = get_sheets_service()
    ensure_headers(service, sheet_id)
    existing = fetch_existing_urls(service, sheet_id)
    append_new_entries(service, sheet_id, items, existing)
    print(f"Done! Published {len(items)} items.")

if __name__ == "__main__":
    main()
