# Notion Scraper Directive

## Goal
Scrape internships manually added to a Notion Database. This serves as a "Human-in-the-Loop" source for high-quality or hard-to-scrape internships (e.g. Unstop, WhatsApp findings).

## Input
- **Environment Variables**:
  - `NOTION_TOKEN`: Integration token (secret_...).
  - `NOTION_DATABASE_ID`: ID of the database to query.

## Output
- **File**: `.tmp/notion_clean.json`
- **Schema**:
  ```json
  [
    {
      "title": "Software Intern",
      "company": "Google",
      "location": "Bangalore",
      "url": "https://careers.google.com/...",
      "source": "Notion (Manual)",
      "posted_time": "2023-10-27"
    }
  ]
  ```

## Notion Database Schema (Expected)
The Notion database should have these properties:
- **Title** (Title): Role Name
- **Company** (Text/Select): Company Name
- **URL** (URL): Application Link
- **Location** (Text/Select): Location (Optional)
- **Status** (Select): "Active", "Closed" (Optional - filter for Active)

## Execution Logic
1. Authenticate with `NOTION_TOKEN`.
2. Query database `NOTION_DATABASE_ID`.
3. Filter for Status != "Closed" (if property exists).
4. Map properties to standard JSON schema.
5. Save to `.tmp/notion_clean.json`.
