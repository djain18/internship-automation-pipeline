# Scrape Niche Communities

## Goal
Scrape internship listings from curated niche communities. **Precision > Coverage** — quality signals are stronger here than mass platforms.

---

## Target Sites

| Site | URL | Focus |
|------|-----|-------|
| Lawctopus | `https://www.lawctopus.com/category/opportunities-events/internships-small-projects/` | Law/Legal internships |
| LawBhoomi | `https://lawbhoomi.com/category/internship-opportunities/` | Law internships/jobs |

---

## Hard Rule
**Precision > Coverage**

- These are curated sources; most listings are legitimate
- Do not apply aggressive filtering that might discard valid entries
- Focus on proper extraction over volume

---

## Site-Specific Notes

### Lawctopus
- Premier legal internship aggregator in India
- Well-structured listings with deadlines
- Categories: Courts, Law Firms, Corporates, NGOs

### LawBhoomi
- Legal career resources for law students
- Internships, jobs, and courses
- NLU graduate-run platform

### Internshala
- Largest internship platform in India
- All categories including tech, marketing, design
- Well-structured API-like data

### Wellfound (formerly AngelList)
- Startup ecosystem jobs
- Founder's office and early-stage roles
- May require filtering for India

---

## Tools

### Primary
- **Tool:** Firecrawl API
- **Endpoint:** `POST /v1/scrape`
- **Best for:** Static/SSR sites with structured HTML

### Fallback
- **Actor:** Apify Web Scraper (`apify/web-scraper`)
- **Use when:** Firecrawl returns empty or malformed data

### JS-Heavy Sites
- **Tool:** Browserless + Playwright
- **Use when:** Sites require JavaScript rendering for content
- **Endpoint:** `wss://chrome.browserless.io`

---

## Output Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | string | Yes | Internship/role title |
| company | string | Yes | Company name |
| location | string | No | City or Remote |
| url | string | Yes | Direct listing URL |
| source | string | Yes | Source site name |
| category | string | No | Role category (Legal, Startup, etc.) |

---

## File Outputs

| File | Purpose |
|------|---------|
| `.tmp/lawctopus_raw.json` | Raw data from Lawctopus |
| `.tmp/lawbhoomi_raw.json` | Raw data from LawBhoomi |
| `.tmp/internshala_raw.json` | Raw data from Internshala |
| `.tmp/wellfound_raw.json` | Raw data from Wellfound |
| `.tmp/niche_clean.json` | Combined, normalized records |

---

## Post-Scrape Validation
1. **Required fields:** Title + URL must be non-empty
2. **Dedup:** Remove duplicate URLs across sources
3. **Source tagging:** Each entry must have source field populated
