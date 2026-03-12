# Score and Deduplicate Internships

## Goal
Aggregate all scraped internships, deduplicate across sources, and rank by quality score. **Pure deterministic Python logic** — no external APIs.

---

## Input Files

| File | Source |
|------|--------|
| `.tmp/linkedin_posts_clean.json` | LinkedIn Posts |
| `.tmp/linkedin_jobs_clean.json` | LinkedIn Jobs |
| `.tmp/niche_clean.json` | Niche Communities |
| `.tmp/unstop_clean.json` | Unstop |
| `.tmp/company_clean.json` | Company Careers |
| `.tmp/gov_clean.json` | Government Portals |

---

## Scoring Factors

### 1. Source Priority (max 30 pts)

| Source | Points |
|--------|--------|
| LinkedIn Posts | 30 |
| LinkedIn Jobs | 25 |
| Niche Communities | 20 |
| Unstop | 15 |
| Company Career Pages | 15 |
| Government Portals | 10 |

### 2. Freshness (max 25 pts)

| Age | Points |
|-----|--------|
| < 6 hours | 25 |
| 6-12 hours | 20 |
| 12-24 hours | 15 |
| 24-48 hours | 10 |
| > 48 hours | 5 |

### 3. Competition (max 25 pts)
*Applies to LinkedIn Jobs only*

| Applicants | Points |
|------------|--------|
| < 50 | 25 |
| 50-100 | 20 |
| 100-200 | 15 |
| 200-300 | 10 |
| > 300 | 5 |

### 4. Engagement (max 20 pts)
*Applies to LinkedIn Posts only*

| Score | Points |
|-------|--------|
| engagement_score >= 3 | 20 |
| engagement_score == 2 | 15 |
| engagement_score == 1 | 10 |
| engagement_score == 0 | 5 |

---

## Deduplication Rules

1. **URL-based:** Exact URL match = duplicate
2. **Fuzzy match:** Same company + similar title (>80% similarity) = potential duplicate
3. **Priority:** Keep the entry from the highest-priority source

---

## Output

| File | Content |
|------|---------|
| `.tmp/final_ranked_internships.json` | All internships, deduped, sorted by score (desc) |

### Output Schema

| Field | Description |
|-------|-------------|
| title | Role title |
| company | Company name |
| location | Location |
| url | Application URL |
| source | Origin source |
| score | Calculated quality score |
| score_breakdown | Breakdown by factor |

---

## Tool Selection
- **No external tools required**
- Pure Python: `json`, file I/O, string matching
- Optional: `difflib` for fuzzy title matching
