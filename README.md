# 🚀 Internship & Lead Automation Pipeline

An end-to-end, serverless data pipeline that finds, parses, scores, and publishes high-value internship and job opportunities from platforms like LinkedIn to a clean Google Sheet dashboard.

Powered by **Python, Modal (serverless execution), Apify (scraping), LLMs (OpenAI/OpenRouter for data extraction), and Google Sheets API.**

---

## ✨ Features

- **Automated LinkedIn Extraction**: Uses Apify constraints to scrape fresh job postings from targeted queries (e.g., "Founder's Office Intern", "SDE Intern", "AI Engineer").
- **LLM-Powered Parsing**: Runs raw post strings through an LLM (e.g., OpenAI/GPT-120b) to cleanly extract structured data: `Company`, `Role`, `Stipend`, `Location`, `Experience`, `Contact Email`, and `Apply Link`.
- **Smart Deduplication & Scoring**: Automatically ranks leads based on keyword intent, recency (bonus for last 24h), and removes spam/stale posts and exact duplicates.
- **Serverless Cloud Execution via Modal**: Runs on a scheduled daily CRON (9:00 PM IST) fetching 130 leads per day, or via targeted one-time webhooks, streaming real-time logs directly.
- **Auto-Sync to Google Sheets**: Idempotent push to a live Google Sheet using OAuth credentials, so stakeholders always have the top N fresh leads at a glance.

---

## 🏗️ Architecture

1. **`scrape_linkedin_posts.py`**
   * Uses targeted queries and Apify's actor.
   * Has a fallback scraper in case the primary scraper hits rate limits.
   * Passes data directly to the LLM analyzer to build schemas.
2. **`llm_post_analyzer.py`**
   * Configurable provider (OpenRouter/OpenAI/Gemini/Groq).
   * Verifies high-intent properties to weed out "job-seeking" story posts and parse out hidden emails/forms.
3. **`aggregate_and_score.py`**
   * Scores posts by matching positive hiring signals. Apply thresholds.
4. **`publish_to_sheets.py`**
   * Checks `token.json` (or uses `credentials.json` fallback locally) and pushes JSON rows cleanly formatted to Sheets.
5. **`modal_app.py`**
   * Packages all deps inside an isolated Debian environment and schedules cron execution.

---

## 📦 Setup & Installation

**1. Clone the repository**
```bash
git clone https://github.com/your-username/internship-automation.git
cd internship-automation
```

**2. Setup Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt # (Add standard deps: apify-client, google-api-python-client, openai, etc.)
```

**3. Configure Environment Variables**
Create a `.env` file in the root directory:
```env
APIFY_API_TOKEN=your_apify_token
GOOGLE_SHEET_ID=your_sheet_id
OPENAI_API_KEY=your_openai_key
...
```

**4. Google Sheets Credentials**
* Generate an OAuth `credentials.json` from the Google Cloud Console (Drive + Sheets scopes).
* Place it in the root folder. Running the script locally the first time will generate `token.json`.

---

## 🚀 Running the Pipeline

**Local Targeted Run**
```bash
python one_time_founders_run.py
```
*(An example script that runs 8 specialized queries in Chennai/Bangalore/Remote India environments).*

**Deploying to Cloud / Modal**
```bash
modal setup
modal deploy modal_app.py
```
This setups a daily Cron job running the whole pipeline natively in the cloud. You can also trigger it manually:
```bash
curl https://your-workspace--internship-pipeline-run-now.modal.run
```

---

## 🛡️ Best Practices Built-In

* **Fallback APIs**: Switches Apify actors if an unexpected API schema change breaks extraction.
* **Cost Efficiency**: Modal runs shut down instantly to save money; LLM payloads use optimized batch requests limit parameters.
* **Separation of Concerns**: Deterministic Python handles the APIs, Probabilistic LLMs handle schema fitting, avoiding "agent loops" taking wrong actions.

---
*Built to automate lead ingestion and prove the value of Serverless AI Agents.*
