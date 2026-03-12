# 🚀 Internship Automation: Project Master Guide

**Version:** 2.0 (Cloud-Native + AI Enhanced)  
**Status:** ✅ Fully Operational  
**Schedule:** Daily at 3:45 PM IST (Modal Cloud)

---

## 1. System Overview
This system automates the discovery, verification, and aggregation of internships from multiple sources, prioritizing quality over quantity using LLM analysis.

### The Pipeline Flow:
1.  **Orchestration**: `run_pipeline.py` (Local) / `modal_app.py` (Cloud) triggers specific scrapers.
2.  **Extraction**:
    *   **LinkedIn Posts**: Iterative loop + Gemini Flash LLM.
    *   **Niche Sites**: Cheerio scrapers (Lawctopus, etc.).
    *   **Company/Govt**: Lever/Greenhouse APIs and custom parsers.
3.  **Refinement**: `aggregate_and_score.py` normalizes data, removes duplicates, and enforces the "60 Total" quota.
4.  **Publishing**: `publish_to_sheets.py` pushes clean data to Google Sheets.

---

## 2. Core Directives & Documentation

### 🧠 Intelligence & Strategy (NEW)
*   **[LLM Intelligence Engine](directives/llm_intelligence_engine.md)**: How Gemini extracts Roles/Companies and detects Fraud.
*   **[Iterative Search Strategy](directives/iterative_search_strategy.md)**: The "Quota-First" scraping loop logic.
*   **[Cloud Deployment](directives/cloud_deployment.md)**: Modal setup and secrets management.

### 🛠 Scraper Components
*   **LinkedIn Posts**: [`directives/scrape_linkedin_posts.md`](directives/scrape_linkedin_posts.md)
*   **LinkedIn Jobs**: *Deprecated/Removed* (File Deleted)
*   **Niche Communities**: [`directives/scrape_niche_communities.md`](directives/scrape_niche_communities.md)
*   **Unstop (Notion)**: [`directives/scrape_notion.md`](directives/scrape_notion.md)
*   **Company Careers**: [`directives/scrape_company_careers.md`](directives/scrape_company_careers.md)

### ⚙️ Processing & Output
*   **Aggregation Logic**: [`directives/score_and_deduplicate.md`](directives/score_and_deduplicate.md)
*   **Sheet Publishing**: [`directives/publish_to_google_sheets.md`](directives/publish_to_google_sheets.md)
*   **Self-Healing**: [`directives/self_annealing_rules.md`](directives/self_annealing_rules.md)

---

## 3. Daily Quota System (Target: 60)
The pipeline is designed to fill a strict quota to avoid overwhelming the user.

| Priority | Source | Target | Logic |
| :--- | :--- | :--- | :--- |
| **1 (High)** | **LinkedIn Posts** | **40** | Scraped first. Stopped when 40 verified found. |
| **2 (Med)** | **Niche Sites** | **10** | Law/Govt/Fresher sites. |
| **3 (Med)** | **Unstop (Manual)** | **5** | High-quality manual entries via Notion. |
| **4 (Low)** | **Company/Govt** | **Remainder** | Backfill if other sources fail to reach 60. |

---

## 4. Maintenance & Debugging
*   **Cloud Run URL**: [Modal Dashboard Link](https://modal.com/apps/dakshinjain187/main/deployed/internship-pipeline)
*   **Logs**: Check `modal run` logs for "LLM Verification" status.
*   **Secrets**: Update `apify_api_token` or `gemini_api_key` in `.env` and redeploy using `modal deploy`.

---

## 5. Recent Upgrades (v2.0)
*   ✅ **Gemini 2.5 Flash Integration**: Faster, cheaper, smarter.
*   ✅ **Few-Shot Extraction**: Now extracts specific roles ("React Intern") and Company Names.
*   ✅ **Scam Shield**: Auto-rejects "pay-to-work" schemes.
*   ✅ **Iterative Looping**: Saves 80% of API costs by stopping early.
