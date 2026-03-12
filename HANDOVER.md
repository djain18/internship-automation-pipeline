# FTB Internship Automation - Handover Guide

This system automates the scraping, verification, and publishing of internships from **LinkedIn**, **Websites**, and **Notion** to a **Google Sheet**.

---

## 🏗️ System Overview

The pipeline consists of three main parts:
1.  **Sources**:
    -   **LinkedIn Posts**: Scraped via Apify.
    -   **Websites**: Scraped via direct HTML parsing (`ngobox.org`, etc.).
    -   **Manual Input**: Pasted into a **Notion Page** ("Cloud Clipboard").
2.  **Analysis (The Brain)**:
    -   Uses **OpenAI (gpt-4o-mini)** to read each post.
    -   **Filters**: India-based, Fresh (< 7 days), Paid/Relevant.
    -   **Extracts**: Role, Company, Location.
3.  **Output**:
    -   **Google Sheet**: Appends new, verified internships. Checks for duplicates.

---

## 🛠️ Prerequisites

To run this system, you need keys for the following services in your `.env` file:

| Service | Variable | Purpose | Cost |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `OPENAI_API_KEY` | Analyzing posts (Intelligence). | ~$2/mo |
| **Apify** | `APIFY_API_TOKEN` | Scraping LinkedIn. | ~$30/mo |
| **Notion** | `NOTION_TOKEN` | Reading the manual input page. | Free |
| **Google** | `GOOGLE_SHEET_ID` | The destination sheet. | Free |
| **Google** | `credentials.json` | For authentication (OAuth). | Free |

---

## 🚀 How to Run

### Option 1: The "Daily Driver" (LinkedIn Search)
This script scrapes **60 verified internships** from LinkedIn based on keywords like "finance intern", "marketing intern", etc.

```bash
python execution/temp_mnc_run.py
```

### Option 2: The "Custom List" (Specific Companies/Sites)
This script checks the specific LinkedIn pages (e.g., `groundzerocommunity`) and websites (`ngobox.org`) you defined.

```bash
python execution/scrape_custom_sources.py
```

### Option 3: The "Cloud Clipboard" (Notion)
This script reads whatever text you pasted into your linked Notion Page.

```bash
python execution/scrape_notion.py
```

---

## 📂 File Structure

-   `execution/`
    -   `temp_mnc_run.py`: Main LinkedIn scraper.
    -   `scrape_custom_sources.py`: Scrapes your specific list of sites/pages.
    -   `scrape_notion.py`: Reads from Notion.
    -   `llm_post_analyzer.py`: The AI logic (uses OpenAI).
    -   `publish_mnc_run.py`: Pushes data to Google Sheets.
-   `.env`: Stores your API keys (Keep this secret!).
-   `credentials.json`: Google Cloud credentials file.

---

## 🔧 Maintenance

-   **Updating Keywords**: Edit `execution/temp_mnc_run.py` to change prompt keywords.
-   **Adding Custom Sites**: Edit `execution/scrape_custom_sources.py` to add new URLs to `LINKEDIN_URLS` or `WEBSITES`.
-   **Changing Quota**: Edit `TARGET_VERIFIED = 60` in `execution/temp_mnc_run.py`.

---

**Handover Date**: February 2026
**Status**: Fully Operational
