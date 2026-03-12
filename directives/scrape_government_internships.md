# Scrape Government Internships

## Goal
Scrape internship listings from trusted Indian government portals. **Only official sources** — no third-party aggregators.

---

## Trusted Sources

| Portal | URL | Focus |
|--------|-----|-------|
| NITI Aayog | `https://www.niti.gov.in/career` | Policy internships |
| RBI | `https://www.rbi.org.in/Scripts/Aborbi.aspx` | Finance/Banking |
| ISRO | `https://www.isro.gov.in/careers.html` | Science/Engineering |
| MyGov | `https://www.mygov.in/` | Various government programs |
| National Informatics Centre | `https://internship.negd.in/` | IT/Digital governance |

---

## Legitimacy Validation Rules

### Must Have
1. **Official domain:** `.gov.in` or `.nic.in` only
2. **Clear application process:** Form, email, or portal link
3. **Named organization:** Must be identifiable ministry/department

### Red Flags (Discard)
- Third-party job boards claiming government roles
- No official seal or letterhead mentioned
- Requires payment or registration fee
- Suspicious redirect URLs

---

## Tools

### Primary
- **Tool:** Firecrawl API
- **Endpoint:** `POST /v1/scrape`
- **Best for:** Standard HTML government pages

### Fallback
- **Tool:** Zyte API
- **Use when:** Anti-bot protection blocks Firecrawl
- **Handles:** WAF, CAPTCHA, rate limiting

---

## Output Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | string | Yes | Internship/role title |
| department | string | Yes | Ministry/Department name |
| location | string | No | City or "Pan India" |
| deadline | string | No | Application deadline |
| url | string | Yes | Official application URL |
| eligibility | string | No | Qualification requirements |

---

## File Outputs

| File | Purpose |
|------|---------|
| `.tmp/gov_raw.json` | Raw scraped data |
| `.tmp/gov_clean.json` | Validated, normalized records |

---

## Post-Scrape Validation
1. **Domain check:** URL must contain `.gov.in` or `.nic.in`
2. **Required fields:** Title + URL must be non-empty
3. **Dedup:** Remove duplicate URLs
4. **Source tagging:** Add portal name as source
