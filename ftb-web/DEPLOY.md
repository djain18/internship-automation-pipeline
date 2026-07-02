# Dispatch — Deployment Guide

## What was built

| Layer | Location | Purpose |
|---|---|---|
| Frontend | `ftb-web/` | Vite + React, Dispatch newspaper design |
| Backend API | `api/` | FastAPI, reads Google Sheets, sends welcome emails |
| Automation | `run_pipeline.py` | Existing Modal pipeline (unchanged) |

---

## Step 1 — Set up Google Sheets for the API

1. Open your existing Google Sheet (the one the pipeline writes to)
2. Click **Share → General access → Anyone with the link → Viewer**
3. Copy the **Sheet ID** from the URL: `docs.google.com/spreadsheets/d/SHEET_ID/...`
4. Go to [console.cloud.google.com](https://console.cloud.google.com)
5. Create a project → Enable **Google Sheets API**
6. Go to **Credentials → API Key** → copy it

---

## Step 2 — Set up Resend (free email)

1. Sign up at [resend.com](https://resend.com) (free: 3,000 emails/month)
2. Add your domain or use their sandbox for testing
3. Copy your **API key** (starts with `re_`)
4. Go to **Audiences → Create audience** → copy the **Audience ID**

---

## Step 3 — Deploy the backend (Railway)

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Point to the `api/` folder (or deploy the whole repo and set Root Directory to `api`)
3. Set environment variables:

```
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_API_KEY=your_api_key
RESEND_API_KEY=re_xxxx
RESEND_AUDIENCE_ID=your_audience_id
FROM_EMAIL=drop@yourdomain.com
FRONTEND_ORIGIN=https://your-project.vercel.app
```

4. Railway auto-detects the `Procfile` and starts: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Copy the deployed URL (e.g. `https://dispatch-api-production.up.railway.app`)

---

## Step 4 — Deploy the frontend (Vercel)

1. Push to GitHub
2. Go to [vercel.com](https://vercel.com) → New Project → select this repo
3. Set **Root Directory** to `ftb-web`
4. Add environment variable:

```
VITE_API_URL=https://your-railway-url.up.railway.app
```

5. Deploy. Vercel picks up `vercel.json` automatically.

---

## Step 5 — Local development

```bash
# Frontend
cd ftb-web
cp .env.example .env.local     # set VITE_API_URL=http://localhost:8000
npm install
npm run dev                    # http://localhost:3000

# Backend (separate terminal)
cd api
pip install -r requirements.txt
cp .env.example .env           # fill in values (or leave blank for seed data)
uvicorn main:app --reload      # http://localhost:8000
```

The frontend falls back to seed data automatically if the API is unreachable.

---

## Architecture decisions

- **Google Sheets as the database** — the pipeline already writes there, zero extra infra
- **Resend for email + contacts** — one service handles both delivery and audience management
- **Seed data fallback** — the site works without a backend (useful for Vercel preview deploys)
- **GSAP free tier** — ScrollTrigger and core GSAP are free/open-source
