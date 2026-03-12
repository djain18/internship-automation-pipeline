# Scrape Unstop Internships

## Goal
Scrape internship listings from Unstop (formerly Dare2Compete) with strong quality filtering.

---

## Filters

| Filter | Value |
|--------|-------|
| Type | Internships only (not competitions, quizzes, etc.) |
| Status | Active/Open applications only |
| Location | India (remote or on-site) |

---

## Quality Checks

### Role Clarity
A listing qualifies only if:
- Title explicitly mentions role (e.g., "Marketing Intern", "SDE Intern")
- Duration is specified (weeks/months)
- Responsibilities or requirements are listed

### Company Legitimacy
Discard if:
- Company name is generic ("ABC Company", "XYZ Pvt Ltd" with no details)
- No company logo or profile
- Zero followers/engagement on Unstop

---

## Target URLs

| URL | Purpose |
|-----|---------|
| `https://unstop.com/internships` | Main internship listings |
| `https://unstop.com/internships?oppstatus=open` | Open applications only |

---

## Tools

### Primary
- **Actor:** Apify Web Scraper (`apify/web-scraper`)
- **Platform:** Apify
- **Use:** Custom page function to extract structured data

### Fallback
- **Tool:** Firecrawl API
- **Endpoint:** `POST /v1/scrape`
- **Use when:** Apify fails or returns malformed data

---

## Output Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | string | Yes | Internship title |
| company | string | Yes | Company name |
| location | string | Yes | City or Remote |
| stipend | string | No | Compensation if mentioned |
| duration | string | No | Internship duration |
| deadline | string | No | Application deadline |
| url | string | Yes | Direct listing URL |
| posted_date | string | No | When posted |

---

## File Outputs

| File | Purpose |
|------|---------|
| `.tmp/unstop_raw.json` | Raw scraped data |
| `.tmp/unstop_clean.json` | Filtered, normalized records |

---

## Post-Scrape Validation
The execution script must:
1. **Type filter:** Discard non-internship entries (competitions, hackathons)
2. **Status filter:** Discard closed/expired listings
3. **Quality check:** Ensure title + company are non-empty
4. **Dedup:** Remove duplicate URLs
