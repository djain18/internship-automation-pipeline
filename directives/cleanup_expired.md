# Cleanup Expired Internships

## Goal
Remove internship listings older than 4 days from Google Sheets to ensure only fresh opportunities are displayed on the website.

## Schedule
- **Run Time:** 10:00 PM IST (Second daily run)
- **Trigger:** Modal cron job (`modal_app.py` → `evening_cleanup_run`)

## Logic
1. Connect to Google Sheets using OAuth credentials
2. Read all rows from the sheet
3. Parse the "Posted" or "Added On" column for date
4. Identify rows where the date is > 4 days ago
5. Delete those rows using batch delete API
6. Log removed entries for audit

## Configuration
- **MAX_AGE_DAYS:** 4 (configurable in `cleanup_expired.py`)
- **Date Parsing:** Supports multiple formats including relative time ("2 days ago")

## Output
- Console log of removed listings
- Updated Google Sheet with only fresh (<4 days) listings

## Related Files
- **Script:** `execution/cleanup_expired.py`
- **Scheduler:** `modal_app.py` → `evening_cleanup_run()`
