# Cloud Deployment Guide

## Goal
Run the internship pipeline **2 times daily** at scheduled times, fetching ~60 internships per run (120 total/day).

---

## Recommended Options (Free/Cheap)

### Option 1: Modal (BEST - RECOMMENDED)
**Best for:** Serverless execution, fast cold starts, pay-per-second
**Cost:** ~$0-2/month (generous free tier)

**Pros:**
- Fast cold starts (< 1 second)
- Pay only when running
- Built-in cron scheduling
- Webhook triggers for manual runs
- Easy secrets management
- Great observability

**Setup time:** 10 minutes

---

### Option 2: GitHub Actions (FREE)
**Best for:** Simple scheduling, no server management
**Cost:** FREE (2000 minutes/month for private repos)

**Pros:**
- Completely free
- No server to manage
- Secrets management built-in

**Cons:**
- Slower cold starts
- May have queue delays

---

### Option 3: Render.com Cron Jobs (FREE)
**Best for:** Simple cron scheduling
**Cost:** FREE for cron jobs

---

### Option 4: Local + Cloudflare Tunnel (FREE but always-on)
**Best for:** Zero-cost, existing hardware
**Cost:** FREE
**Requirement:** Machine must stay on 24/7

---

## Setup: GitHub Actions (Recommended)

### Step 1: Push to GitHub

```bash
# Initialize git (if not done)
git init
git add .
git commit -m "Initial commit"

# Create GitHub repo and push
gh repo create internship-pipeline --private --push
# OR manually create on github.com and:
git remote add origin https://github.com/YOUR_USERNAME/internship-pipeline.git
git push -u origin main
```

### Step 2: Add Secrets

Go to: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

Add these secrets:
| Secret Name | Value |
|-------------|-------|
| `APIFY_API_TOKEN` | Your Apify token |
| `FIRECRAWL_API_KEY` | Your Firecrawl key |
| `BROWSERLESS_API_KEY` | Your Browserless key |
| `ZYTE_API_KEY` | Your Zyte key |
| `GOOGLE_SHEET_ID` | Your Sheet ID |
| `GOOGLE_CREDENTIALS_JSON` | Contents of credentials.json |
| `GOOGLE_TOKEN_JSON` | Contents of token.json |

### Step 3: Create Workflow File

Create `.github/workflows/run_pipeline.yml` (already created below)

### Step 4: Set Your Schedule

Edit the cron expressions in the workflow file:
- `'30 4 * * *'` = 10:00 AM IST (4:30 UTC)
- `'30 12 * * *'` = 6:00 PM IST (12:30 UTC)

**Cron format:** `minute hour day month weekday`

---

## Cost Comparison

| Platform | Cost | Runs/Day | Notes |
|----------|------|----------|-------|
| GitHub Actions | FREE | Unlimited | 2000 min/month |
| Railway | FREE | ~10 | $5 credit/month |
| Render | FREE | Unlimited | Cron jobs free |
| Google Cloud Run | ~$1/month | Unlimited | Free tier |
| AWS Lambda | ~$0 | Unlimited | Free tier |
| Heroku | $5/month | Unlimited | No free tier |

---

## Adjusting for 60 Internships/Run

Update the scraper configs to fetch more results:

| Scraper | Current | Recommended |
|---------|---------|-------------|
| LinkedIn Jobs | 100 | 50 |
| LinkedIn Posts | 100 | 30 |
| Niche Sites | ~20 | 20 |
| Unstop | ~20 | 20 |
| Company Careers | ~10 | 10 |
| Government | ~5 | 5 |

**Expected per run:** ~60-80 internships (before dedup)
**After dedup:** ~40-60 unique internships

---

## Monitoring

1. **GitHub Actions:** Check `Actions` tab for run history
2. **Google Sheet:** New rows appear after each run
3. **Logs:** `.tmp/pipeline_log.json` (in repo)

---

## Quick Start Commands

```bash
# Test locally first
python execution/run_pipeline.py

# Quick test (LinkedIn only)
python execution/run_pipeline.py --quick

# Push and let GitHub Actions run
git add .
git commit -m "Update pipeline"
git push
```
