"""
format_google_sheet.py
-----------------------
Professional formatting utility for Google Sheets.
Applies headers, frozen rows, zebra stripes, and auto-resizing.
"""

import os
import sys
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import execution.publish_to_sheets as pub_utils

def apply_formatting(spreadsheet_id: str, sheet_name: str = "Sheet1"):
    print(f"Applying professional formatting to: {spreadsheet_id}")
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
        # 1. Freeze first row
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1}
                },
                "fields": "gridProperties.frozenRowCount"
            }
        },
        # 2. Format Header (Row 1) - Bold, White text, Deep Blue background, Center align
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.29, "green": 0.52, "blue": 0.91}, # #4A86E8
                        "horizontalAlignment": "CENTER",
                        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }
        },
        # 3. Add Zebra Stripes (Alternating colors)
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=ISEVEN(ROW())"}]},
                        "format": {"backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}}
                    }
                },
                "index": 0
            }
        },
        # 4. Center Align Data Columns (Rank, Score, Stipend, Duration, Type, Timing, Deadline)
        # Column A (0), B (1), G(6), H(7), I(8), J(9), K(10)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment"
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 6, "endColumnIndex": 11},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment"
            }
        },
        # 5. Auto-resize all columns
        {
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 18}
            }
        },
        # 6. Add Filter to Header
        {
            "setBasicFilter": {
                "filter": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 500} # Adjust max rows as needed
                }
            }
        }
    ]

    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()
        print("✅ Success! Professional formatting applied.")
    except Exception as e:
        print(f"❌ Error applying formatting: {e}")

if __name__ == "__main__":
    # Founders & AI sheet
    founders_sheet = "1SI28rbwXo2N063_94ftp3biqNrmjVio0Xp3SXEix3WE"
    # Nightly run sheet
    nightly_sheet = "1f6b_QgkmeOAu0XFpiYyDHMgfkXFKEsrX4gl8IjWbI1k"
    
    apply_formatting(founders_sheet)
    apply_formatting(nightly_sheet)
