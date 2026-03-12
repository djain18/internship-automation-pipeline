# Scrape Company Career Pages

## Goal
Scrape internship listings directly from company career pages. Target companies with known internship programs.

---

## Input: Target Companies

Maintain a list of companies to scrape in the execution script. Default targets:

| Company | Career URL | ATS |
|---------|-----------|-----|
| Razorpay | `https://razorpay.com/jobs/` | Lever |
| Zerodha | `https://zerodha.com/careers/` | Custom |
| Flipkart | `https://www.flipkartcareers.com/` | Workday |
| Swiggy | `https://careers.swiggy.com/` | Greenhouse |
| CRED | `https://careers.cred.club/` | Lever |
| Groww | `https://groww.in/careers` | Lever |
| PhonePe | `https://www.phonepe.com/careers/` | Custom |
| Meesho | `https://meesho.io/careers` | Greenhouse |

---

## ATS Handling Rules

### Lever
- Jobs usually at `/jobs` endpoint
- JSON available at `[career_url]/jobs?filter=internship`
- Look for `commitment: "Intern"` field

### Greenhouse
- Jobs at `/jobs` or embedded iframe
- Filter by `department` or `job_type`
- May need to scrape main page + detail pages

### Workday
- Heavy JavaScript rendering
- Use Browserless for these
- Look for `job-posting` elements

### Custom
- Parse HTML structure
- Look for `intern` keyword in title/description

---

## Tools

### Primary
- **Tool:** Firecrawl API
- **Best for:** Lever, Greenhouse (server-rendered)

### Fallback
- **Tool:** Browserless + Playwright
- **Use for:** Workday, heavy JS sites
- **Endpoint:** `wss://chrome.browserless.io`

---

## Output Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | string | Yes | Role title |
| company | string | Yes | Company name |
| location | string | No | Office location |
| url | string | Yes | Direct job URL |
| ats | string | No | ATS platform detected |

---

## File Outputs

| File | Purpose |
|------|---------|
| `.tmp/company_raw.json` | Raw scraped data |
| `.tmp/company_clean.json` | Internship-only, normalized |

---

## Post-Scrape Filters
1. **Internship only:** Title must contain "intern" (case-insensitive)
2. **Dedup:** Remove duplicate URLs
3. **Required fields:** Title + Company + URL must be non-empty
