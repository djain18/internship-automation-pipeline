# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two systems that meet at **one Google Sheet**:

1. **Automation pipeline** (Python) — every night scrapes LinkedIn hiring posts, scores them with an LLM, and writes clean internship rows to a Google Sheet.
2. **Rise website** — a public site where students browse and apply to those internships. `api/` (FastAPI) reads the sheet; `rise-web/` (React) is the front end.

```
[Pipeline]  run_pipeline.py → Apify scrape → LLM extract/score → publish_to_sheets.py ─┐
                                                                                        ├─► GOOGLE SHEET ("RISE Internships")
[Website]   rise-web (Vercel) ──VITE_API_BASE──► api/ (Railway) ──GOOGLE_API_KEY──read──┘
```

The Sheet is the **only** coupling between the two. They share `GOOGLE_SHEET_ID`; the pipeline writes via OAuth (`credentials.json`/`token.json`), the API reads via a public API key (sheet must be "anyone with link can view").

## Orchestrator philosophy (how to operate here)

- **Execute, never simulate.** Solve by running the deterministic Python in `execution/`, not by hand-reasoning outputs.
- **Tool-first:** before writing new code, check `execution/` for an existing script (reuse if ~80% match).
- **Self-anneal on failure:** read the stack trace → patch → re-run → if a permanent constraint is found, update the relevant `directives/*.md`.
- **File hygiene:** inputs from `directives/`; intermediates to `.tmp/`; secrets via `os.environ`; outputs to the Sheet.
- A task is done only when verification passes (the script runs clean and the Sheet/site reflect it).

## Commands

### Automation pipeline (repo root)
```bash
pip install -r requirements.txt
python run_pipeline.py                 # full local run: scrape → score → publish to Sheet
python sync_secrets.py                 # push .env → Modal secret "internship-secrets"
modal deploy modal_app.py              # deploy + activate nightly cron (11PM IST = 30 17 UTC)
```
`run_pipeline.py` orchestrates `export_sheet_keys.py` → `scrape_linkedin_posts.py` → `publish_to_sheets.py`, retrying in "topup" mode until `TARGET_NEW` (105) net-new internships are added (max 3 passes). There is **no automated test suite** — verify by running and inspecting the Sheet.

### Website API (`api/`)
```bash
cd api && pip install -r requirements.txt
uvicorn main:app --reload --port 8000  # local; needs GOOGLE_SHEET_ID + GOOGLE_API_KEY in env
```
Routes: `GET /api/listings`, `GET /api/stats`, `POST /api/subscribe`, `GET /health`. Deploys to **Railway** (`api/Procfile`). Falls back to `api/seed_listings.json` when the Sheet is unreachable.

### Front end (`rise-web/`)
```bash
cd rise-web && npm install
npm run dev                            # set VITE_API_BASE to the API URL (blank = seed data)
npm run build                          # production build → dist/ (deploys to Vercel)
```

## Architecture notes that span files

- **Pipeline scoring/filtering** lives in `execution/llm_post_analyzer.py`: an LLM extracts structured fields and sets `should_include`; posts then pass scam/blacklist/India-eligibility/hiring-signal filters. LLM provider cascades **OpenRouter → Gemini → OpenAI → Groq → regex** based on which API key is set (`configure_llm`).
- **The Sheet schema is 18 columns A–R** (`HEADERS` in `execution/publish_to_sheets.py`; mirrored by `COL` in `api/sheets.py`). Changing columns means editing **both**. `api/sheets.py:_row_to_listing` derives `id`, `cluster`, `score`, and `hoursAgo` on read — those are computed, not stored.
- **Decoupled from ftbhustle:** the pipeline used to also POST every internship to an external `internal.ftbhustle.com` API. That `ingest_to_api()` call was removed — the Sheet is now the single source of truth. Do not reintroduce external pushes.
- **`rise-web/` is the active site.** `ftb-web/` (the "Dispatch" editorial design, custom CSS + GSAP) is **legacy/superseded**; `codenest/` is an unrelated video-hero experiment. Don't edit those when working on the site.
- **`rise-web` design system:** Tailwind with HSL CSS tokens in `src/index.css`, Instrument Serif (display) + Inter (body), indigo accent, frosted-glass panels, Framer Motion for entrance + scroll animations. New sections must match these tokens (never raw colors). Data flows through `src/lib/api.js` (live) with `src/lib/seed.js` fallback; apply actions go through `src/lib/format.js:openApply` (applyLink → postUrl → mailto).

## Environment variables

- **Pipeline** (`.env`, also synced to Modal): `APIFY_API_TOKEN`, one LLM key (`OPENROUTER_API_KEY`/`GEMINI_API_KEY`/`OPENAI_API_KEY`/`GROQ_API_KEY`), `GOOGLE_SHEET_ID`, `GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`.
- **API** (Railway): `GOOGLE_SHEET_ID` (same as pipeline), `GOOGLE_API_KEY`, `RESEND_API_KEY`, `RESEND_AUDIENCE_ID`, `FROM_EMAIL`, `FRONTEND_ORIGIN` (CORS = the Vercel URL).
- **Front end** (Vercel): `VITE_API_BASE` = the Railway API URL.

Note: `.env` is read-protected in this environment — changes to `GOOGLE_SHEET_ID` etc. must be made by the user (and re-synced to Modal).
