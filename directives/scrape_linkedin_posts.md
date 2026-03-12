# Scrape LinkedIn Posts

## Goal
Scrape organic LinkedIn posts from founders, HRs, and hiring managers announcing internship/job openings. This is **Priority 1** — higher priority than LinkedIn Jobs.

---

## Filters

| Filter | Value |
|--------|-------|
| Location | India-based posts/authors |
| Freshness | Prefer < 24 hours old |
| Intent | Must match hiring-intent heuristics |

---

## Hiring-Intent Heuristics

A post qualifies if it contains **2+ of the following signals**:

| Signal | Examples |
|--------|----------| |
| Role type | "intern", "internship" , "internship opportunity"|
| Action words | "apply", "DM", "send resume", "share CV", "drop your resume" |
| Urgency | "immediate", "urgent", "ASAP", "starting soon" |
| Contact method | Email address, form link, "comment below" |

---

## Engagement as Quality Signal

Higher engagement = higher visibility = likely legitimate:

| Metric | Weight |
|--------|--------|
| Likes > 50 | +1 quality point |
| Comments > 10 | +1 quality point |
| Reposts > 5 | +1 quality point |

Posts with **0 engagement** after 12+ hours should be deprioritized.

---

## Tools

### Primary
- **Actor:** `curious_coder/linkedin-post-search-scraper`
- **Platform:** Apify

### Fallback
- **Actor:** `apimaestro/linkedin-posts-search-scraper-no-cookies`
- **Use when:** Primary actor fails or returns empty results

---

## Output Schema

| Field | Type | Description |
|-------|------|-------------|
| author_name | string | Post author name |
| author_headline | string | Author's LinkedIn headline |
| post_text | string | Full post content |
| posted_time | string | When posted |
| likes | int | Like count |
| comments | int | Comment count |
| url | string | Direct post URL |
| hiring_signals | list | Matched heuristic keywords |

---

## File Outputs

| File | Purpose |
|------|---------|
| `.tmp/linkedin_posts_raw.json` | Raw API response |
| `.tmp/linkedin_posts_clean.json` | Filtered, schema-compliant records |

---

## Post-Scrape Filters
The execution script must enforce:
1. **Freshness:** Prefer posts < 24 hours, allow up to 48 hours max
2. **Hiring intent:** Must match 2+ heuristic signals
3. **Engagement sanity:** Flag 0-engagement posts older than 12 hours
