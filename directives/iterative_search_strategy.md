# Iterative Search Strategy (LinkedIn Posts)

**Component:** `execution/scrape_linkedin_posts.py`

## 1. Problem Statement
LinkedIn scraping is expensive (API calls) and prone to noise (unrelated posts). A traditional "scrape all then filter" approach wastes quota.

## 2. The Solution: Iterative Loop
We implemented a **Quota-Driven Loop** that stops scraping the moment we hit our target.

### The Algorithm:
1.  **Initialize**: Set Target = 40 Verified Leads.
2.  **Keyword Loop**: Iterate through a prioritized list of boolean search terms (Group 1: High Intent, Group 2: Tech, etc.).
3.  **Micro-Batch Scrape**:
    *   Scrape only **20 posts** for the current keyword.
    *   *Why?* To minimize API usage if the keyword yields poor results.
4.  **Instant Verification**:
    *   Pass these 20 posts to the **LLM Intelligence Engine**.
    *   Filter out old/spam/irrelevant posts immediately.
5.  **Quota Check**:
    *   Add valid leads to `verified_posts`.
    *   **IF** `len(verified_posts) >= 40`: **BREAK LOOP**.
    *   **ELSE**: Continue to next keyword.

---

## 3. Keyword Groups
Optimized Boolean Strings to maximize relevance per query:

*   **Group 1 (High Intent)**: `(hiring intern india) OR (internship opportunity) OR (apply now internship)`
*   **Group 2 (Tech)**: `(sde intern) OR (software intern) OR (full stack intern) OR (data science intern)`
*   **Group 3 (Business)**: `(product intern) OR (marketing intern) OR (business development intern)`
*   **Group 4 (Niche)**: `(ui ux intern) OR (content intern) OR (finance intern)`

---

## 4. Benefits
*   **Cost Efficiency**: We don't scrape 500 posts to find 40. We might stop after scaping 60 if the yield is high.
*   **Speed**: Faster execution time as we process in small batches.
*   **Quality**: Prioritizes "High Intent" keywords first.
