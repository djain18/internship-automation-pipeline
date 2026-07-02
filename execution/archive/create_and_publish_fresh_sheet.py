"""
create_and_publish_fresh_sheet.py
-----------------------
Utility to create a NEW Google Spreadsheet and publish the 65 verified internships.
Ensures a clean, professionally formatted result.
"""

import os
import sys
import json
from datetime import datetime

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import execution.publish_to_sheets as pub_utils
import execution.format_google_sheet as formatter
from execution.field_clusters import get_subchips, get_similar_fields

def create_fresh_sheet_and_publish(items):
    print("Creating a fresh Google Spreadsheet...")
    service = pub_utils.get_sheets_service()
    
    # 1. Create Spreadsheet
    title = f"Founders Office & AI Automation Internships - FRESH START ({datetime.now().strftime('%b %d')})"
    spreadsheet = {
        'properties': {'title': title}
    }
    spreadsheet = service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
    new_sheet_id = spreadsheet.get('spreadsheetId')
    print(f"✅ Created new sheet: {new_sheet_id}")

    # 2. Publish Data
    # Use the same 'Human' headers mapping
    CUSTOM_HEADERS = [
        "Title", "Type", "Timing", "Description", "Stipend", "Duration",
        "Experience", "Location", "Deadline", "Tags", "HiringOrganization",
        "HiringManager", "Post URL", "Apply Link", "Contact Email", "Date Added",
        "Subchips", "Similar Fields"
    ]

    new_rows = []
    for item in items:
        title = item.get("title") or item.get("role") or ""
        tags = item.get("tags", [])
        new_rows.append([
            title,
            item.get("type", "Internship"),
            item.get("timing", ""),
            item.get("description", ""),
            item.get("stipend", ""),
            item.get("duration", ""),
            item.get("experience", ""),
            item.get("location", ""),
            item.get("deadline", ""),
            ", ".join(tags) if isinstance(tags, list) else tags,
            item.get("hiringOrganization") or item.get("company", ""),
            item.get("author_name") or item.get("author", ""),
            item.get("url") or item.get("source_url", ""),
            item.get("apply_link", ""),
            item.get("contact_email", ""),
            datetime.now().strftime("%Y-%m-%d"),
            get_subchips(title),
            get_similar_fields(title),
        ])

    # Update Headers
    try:
        service.spreadsheets().values().update(
            spreadsheetId=new_sheet_id,
            range="Sheet1!A1:R1",
            valueInputOption="RAW",
            body={"values": [CUSTOM_HEADERS]}
        ).execute()
    except Exception as e:
        print(f"Failed to write headers: {e}")
        return new_sheet_id

    # Append Data
    if new_rows:
        try:
            service.spreadsheets().values().append(
                spreadsheetId=new_sheet_id,
                range="Sheet1!A2",
                valueInputOption="RAW",
                body={"values": new_rows}
            ).execute()
            print(f"✅ Appended {len(new_rows)} items to the fresh sheet.")
        except Exception as e:
            print(f"Failed to append data: {e}")

    # 3. Format Sheet
    formatter.apply_formatting(new_sheet_id)
    
    print("\n" + "="*50)
    print("✨ ALL DONE! Fresh Sheet Ready.")
    print(f"🔗 URL: https://docs.google.com/spreadsheets/d/{new_sheet_id}")
    print("="*50)
    return new_sheet_id

if __name__ == "__main__":
    # Accept an optional file path argument, otherwise use pipeline output then founders fallback
    if len(sys.argv) > 1:
        CLEAN_FILE = sys.argv[1]
    else:
        PIPELINE_FILE = os.path.join(".tmp", "final_ranked_internships.json")
        FOUNDERS_FILE = os.path.join(".tmp", "founders_ai_clean.json")
        CLEAN_FILE = PIPELINE_FILE if os.path.exists(PIPELINE_FILE) else FOUNDERS_FILE

    if os.path.exists(CLEAN_FILE):
        with open(CLEAN_FILE, 'r', encoding='utf-8') as f:
            items = json.load(f)
        print(f"Loaded {len(items)} items from {CLEAN_FILE}")
        create_fresh_sheet_and_publish(items)
    else:
        print("ERROR: No verified items found in cache. Run scraper first.")
