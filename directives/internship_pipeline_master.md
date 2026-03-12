# Internship Pipeline Master Directive

## Overview
Automated pipeline to discover, filter, score, and publish high-quality internship opportunities from multiple sources to a Google Sheet.

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INTERNSHIP PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ 1. SCRAPE    │  │ 2. FILTER    │  │ 3. SCORE     │  │ 4. PUBLISH   │ │
│  │              │──│              │──│              │──│              │ │
│  │ 6 Sources    │  │ Clean Data   │  │ Rank by      │  │ Google       │ │
│  │ → Raw JSON   │  │ → Clean JSON │  │ Quality      │  │ Sheets       │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Source Priority Order

| Priority | Source | Script | Directive |
|----------|--------|--------|-----------|
| 1 | LinkedIn Posts | `scrape_linkedin_posts.py` | `scrape_linkedin_posts.md` |
| 2 | LinkedIn Jobs | `scrape_linkedin_jobs.py` | `scrape_linkedin_jobs.md` |
| 3 | Niche Communities | `scrape_niche_sites.py` | `scrape_niche_communities.md` |
| 4 | Unstop | `scrape_unstop.py` | `scrape_unstop_internships.md` |
| 5 | Company Career Pages | `scrape_company_careers.py` | `scrape_company_careers.md` |
| 6 | Government Portals | `scrape_government.py` | `scrape_government_internships.md` |

---

## Execution Order

### Phase 1: Scraping
Run all scrapers to collect raw data:

```
python execution/scrape_linkedin_posts.py
python execution/scrape_linkedin_jobs.py
python execution/scrape_niche_sites.py
python execution/scrape_unstop.py
python execution/scrape_company_careers.py
python execution/scrape_government.py
```

**Outputs:**
- `.tmp/linkedin_posts_raw.json` → `.tmp/linkedin_posts_clean.json`
- `.tmp/linkedin_jobs_raw.json` → `.tmp/linkedin_jobs_clean.json`
- `.tmp/niche_clean.json`
- `.tmp/unstop_clean.json`
- `.tmp/company_clean.json`
- `.tmp/gov_clean.json`

### Phase 2: Aggregation & Scoring
Combine all cleaned data, deduplicate, and score:

```
python execution/aggregate_and_score.py
```

**Output:**
- `.tmp/final_ranked_internships.json`

### Phase 3: Publishing
Push to Google Sheets (idempotent - no duplicates):

```
python execution/publish_to_sheets.py
```

**Output:**
- Google Sheet updated with ranked internships

---

## Hard Rules

### Quality > Speed
- One verified internship > ten unverified ones
- If unsure about legitimacy, discard

### File Hygiene
- **Intermediates:** All temp files in `.tmp/` only
- **Deliverable:** Google Sheets is the ONLY final output
- **Secrets:** Read from `.env`, never hardcode

### Self-Healing
- See `self_annealing_rules.md` for retry/fallback logic
- On failure: retry → fallback → escalate

---

## Scoring System

| Factor | Max Points | Applied To |
|--------|------------|------------|
| Source Priority | 30 | All sources |
| Freshness | 25 | All sources |
| Competition (applicants) | 25 | LinkedIn Jobs only |
| Engagement | 20 | LinkedIn Posts only |

**Total Max Score: 100 points**

---

## Output Schema (Google Sheet)

| Column | Header | Description |
|--------|--------|-------------|
| A | Rank | Position by score (1 = best) |
| B | Score | Quality score (0-100) |
| C | Title | Internship title |
| D | Company | Company name |
| E | Location | City or Remote |
| F | Source | Origin platform |
| G | URL | Application link |
| H | Posted | When posted |
| I | Added On | Timestamp when added |

---

## Required Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `APIFY_API_TOKEN` | Yes | LinkedIn scrapers |
| `GOOGLE_SHEET_ID` | Yes | Output destination |
| `credentials.json` | Yes | Google OAuth |
| `FIRECRAWL_API_KEY` | Recommended | Niche/Company/Gov scrapers |
| `BROWSERLESS_API_KEY` | Optional | JS-heavy sites |
| `ZYTE_API_KEY` | Optional | Anti-bot sites |

---

## Quick Start

```powershell
# 1. Install dependencies
pip install apify-client python-dotenv google-auth google-auth-oauthlib google-api-python-client requests

# 2. Run full pipeline
python execution/scrape_linkedin_posts.py
python execution/scrape_linkedin_jobs.py
python execution/aggregate_and_score.py
python execution/publish_to_sheets.py
```

---

## Related Directives

| Directive | Purpose |
|-----------|---------|
| `scrape_linkedin_posts.md` | LinkedIn Posts scraping rules |
| `scrape_linkedin_jobs.md` | LinkedIn Jobs scraping rules |
| `scrape_niche_communities.md` | Niche sites (Lawctopus, Internshala, etc.) |
| `scrape_unstop_internships.md` | Unstop platform rules |
| `scrape_company_careers.md` | Direct company career pages |
| `scrape_government_internships.md` | Government portal rules |
| `score_and_deduplicate.md` | Scoring factors and dedup logic |
| `publish_to_google_sheets.md` | Sheet schema and update logic |
| `self_annealing_rules.md` | Retry, fallback, and error handling |

---

## Current State
Pipeline ready. Run test to verify all components.
