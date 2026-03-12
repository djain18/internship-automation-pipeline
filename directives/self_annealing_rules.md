# Self-Annealing Rules

## Goal
Define retry, fallback, and escalation behavior to make the pipeline self-healing and resilient.

---

## Retry Thresholds

| Tool Category | Max Retries | Backoff | Notes |
|---------------|-------------|---------|-------|
| Apify Actors | 3 | Exponential (2s, 4s, 8s) | Check actor status before retry |
| Firecrawl API | 2 | Linear (5s) | May hit rate limits |
| Zyte API | 2 | Linear (10s) | Expensive, minimize calls |
| Browserless | 2 | Linear (5s) | Session may timeout |
| Google Sheets API | 3 | Exponential (1s, 2s, 4s) | Quota-aware |

---

## Tool Fallback Order

### LinkedIn Jobs
1. `valig/linkedin-jobs-scraper` (Primary)
2. `curious_coder/linkedin-jobs-scraper` (Fallback)
3. **Escalate** if both fail

### LinkedIn Posts
1. `curious_coder/linkedin-post-scraper` (Primary)
2. Apify official template (Fallback)
3. **Escalate** if both fail

### Unstop
1. Apify Web Scraper (Primary)
2. Firecrawl API (Fallback)
3. **Escalate** if both fail

### Niche Communities
1. Firecrawl API (Primary)
2. Apify Web Scraper (Fallback)
3. Browserless + Playwright (JS-heavy)
4. **Escalate** if all fail

### Government Portals
1. Firecrawl API (Primary)
2. Zyte API (Fallback - handles WAF)
3. **Escalate** if both fail

### Company Careers
1. Firecrawl API (Primary)
2. Browserless + Playwright (Fallback)
3. **Escalate** if both fail

---

## Human Escalation Conditions

### Immediate Escalation
- API key invalid or expired
- OAuth token refresh fails
- Google Sheet access denied
- All fallbacks exhausted for a source

### Delayed Escalation (After 3 Consecutive Failures)
- Same source fails on 3 consecutive runs
- Error pattern indicates permanent change (site restructured)

### Warning Only (Log & Continue)
- Single source returns 0 results (may be legitimate)
- Rate limit hit but backoff succeeded
- Partial data loss (some pages failed)

---

## Error Classification

| Error Type | Action |
|------------|--------|
| `401 Unauthorized` | Escalate immediately (credentials issue) |
| `403 Forbidden` | Try fallback, then escalate |
| `404 Not Found` | Log warning, skip source |
| `429 Too Many Requests` | Backoff and retry |
| `500+ Server Error` | Retry with backoff |
| `Timeout` | Retry once, then fallback |
| `Connection Error` | Retry with backoff |

---

## Self-Healing Actions

### On Script Failure
1. Read error message and stack trace
2. Check if error is recoverable (network, rate limit)
3. If recoverable: retry with backoff
4. If not: try fallback tool
5. If all fail: log error, continue pipeline with partial data

### On Data Quality Issue
1. Check if `_clean.json` has fewer entries than expected
2. Log warning if < 5 entries from a major source
3. Continue pipeline (don't block on low yield)

### On Dedup Anomaly
1. If dedup removes > 80% of entries: log warning
2. May indicate scraper returning duplicates
3. Flag for review but don't block

---

## Logging Requirements

All errors must log:
- Timestamp
- Source/Script name
- Error type and message
- Action taken (retry/fallback/escalate)
- Outcome (success/fail)
