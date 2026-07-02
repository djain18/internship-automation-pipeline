"""
unhide_sheet_rows.py
-----------------------
Utility to unhide all rows and clear filters in a Google Sheet.
Used to fix visibility issues after structural synchronization.
"""

import os
import sys
from googleapiclient.discovery import build

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import execution.publish_to_sheets as pub_utils

def unhide_and_clear_filters(spreadsheet_id: str, sheet_name: str = "Sheet1"):
    print(f"Forcing visibility on: {spreadsheet_id}")
    service = pub_utils.get_sheets_service()
    
    # 1. Get Sheet ID
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = sheet_metadata.get('sheets', '')
    sheet_id = 0
    for s in sheets:
        if s.get("properties", {}).get("title") == sheet_name:
            sheet_id = s.get("properties", {}).get("sheetId")
            break

    requests = [
        # 1. Unhide all rows
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 5000
                },
                "properties": {"hiddenByUser": False},
                "fields": "hiddenByUser"
            }
        },
        # 2. Clear Basic Filter
        {
            "clearBasicFilter": {
                "sheetId": sheet_id
            }
        }
    ]

    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()
        print("✅ Success! All rows unhidden and filters cleared.")
    except Exception as e:
        # If clearBasicFilter fails because there is no filter, it's fine
        if "no basic filter" in str(e).lower():
            print("No filter to clear, proceeding...")
            # Try just the unhide part
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests[:1]}
            ).execute()
            print("✅ Success! All rows unhidden.")
        else:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    sheet_id = "1SI28rbwXo2N063_94ftp3biqNrmjVio0Xp3SXEix3WE"
    unhide_and_clear_filters(sheet_id)
