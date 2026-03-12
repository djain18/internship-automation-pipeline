# Publish to Google Sheets

## Goal
Publish ranked internships to Google Sheets as the **final deliverable**. Updates must be idempotent — no duplicates on re-runs.

---

## Prerequisites

1. **credentials.json** — Google Cloud OAuth credentials in project root
2. **token.json** — Auto-generated after first OAuth flow
3. **GOOGLE_SHEET_ID** — Target sheet ID in `.env`

---

## Sheet Schema

| Column | Header | Description |
|--------|--------|-------------|
| A | Rank | Position by score (1 = best) |
| B | Score | Quality score |
| C | Title | Internship title |
| D | Company | Company name |
| E | Location | City or Remote |
| F | Source | Origin platform |
| G | URL | Application link |
| H | Posted | When posted (if available) |
| I | Added On | Timestamp when row was added |

---

## Idempotent Update Logic

### On Each Run:
1. **Fetch existing URLs** from column G
2. **Compare** with new data from `final_ranked_internships.json`
3. **Append only new entries** (URL not in existing set)
4. **Update ranks** for all rows based on current scores

### Dedup Key
- Primary: URL (column G)
- If URL missing: Company + Title hash

---

## Tool Selection

- **API:** Google Sheets API v4
- **Auth:** OAuth 2.0 via `credentials.json`
- **Scopes:** `https://www.googleapis.com/auth/spreadsheets`

---

## Input/Output

| Type | Path |
|------|------|
| Input | `.tmp/final_ranked_internships.json` |
| Output | Google Sheet (GOOGLE_SHEET_ID) |

---

## Error Handling

1. **Missing credentials:** Exit with clear error message
2. **API quota:** Implement exponential backoff
3. **Empty input:** Skip update, log warning
