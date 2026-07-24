# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two systems that meet at **one Google Sheet, and now also one Firestore collection**:

1. **Automation pipeline** (Python) — every night scrapes LinkedIn hiring posts, scores them with an LLM, and writes clean internship rows to a Google Sheet. A second Modal cron (`daily_digest`) sends each signed-in student a personalized digest of matching internships every morning.
2. **Rise website** — a public site where students browse and apply to those internships, and can sign in with Google to get the daily digest. `api/` (FastAPI, hosted on **Modal**, not Railway — see below) reads the sheet; `rise-web/` (React) is the front end and also talks to Firestore directly for sign-in preferences.

```
[Pipeline]   run_pipeline.py → Apify scrape → LLM extract/score → publish_to_sheets.py ─┐
                                                                                         ├─► GOOGLE SHEET ("RISE Internships")
[Website]    rise-web (Vercel) ──VITE_API_BASE──► api_web (Modal, modal_app.py) ──read───┘

[Auth]       rise-web ──Firebase Auth (Google)──► Firestore users/{uid} ◄──firebase-admin── daily_digest (Modal cron, 8AM IST)
```

The Sheet is the primary coupling between the pipeline and the website; Firestore is a second, narrower one. They share `GOOGLE_SHEET_ID`; the pipeline writes via OAuth (`credentials.json`/`token.json`), the API reads via Google's keyless CSV export (the sheet must be "anyone with link can view" — `GOOGLE_API_KEY` is **not** used despite older docs implying otherwise). `rise-web` writes signed-in users' digest preferences directly to `users/{uid}` in Firestore (Firebase Auth + schema-validating security rules in `firestore.rules`); the `daily_digest` Modal cron reads that same collection via `firebase-admin`, using a secret (`firebase-admin-key`) scoped separately from the pipeline's own `internship-secrets`.

**`api/` is hosted on Modal, not Railway.** Railway's free trial expired; `api/main.py`'s FastAPI app is now served by the `api_web` function in `modal_app.py` (`@modal.asgi_app()`, its own lightweight image, `min_containers=1` so it doesn't cold-start). `api/Procfile` is dead weight kept only as a Render/Fly fallback reference. A scheduled `api_uptime_check` function (every 30 min) actually `raise`s on failure so Modal's own alerting fires — a prior outage went unnoticed for an unknown period because the frontend's seed-data fallback masked it.

**Two Modal workspaces exist under this account** — `dakshinjain187` (created Feb 28, the real production one — matches this file's own deploy commands) and `fireinthebellyftb` (created Apr 16, a duplicate that was quietly running the same cron in parallel; now stopped via `modal app stop`). Always deploy with `MODAL_PROFILE=dakshinjain187` explicitly set, or check `modal profile list`'s active marker before running `modal deploy` — the wrong profile will silently create/update the decoy instead.

**The old `/api/subscribe` route and `api/email_service.py` no longer exist.** The site's email-capture form (`EmailAlerts.jsx`) was replaced with Google Sign-In; preferences go straight to Firestore from the client, not through the backend. Resend is still used, but only for its transactional send API (`daily_digest` → Resend `/emails`), not its contacts/audience feature.

## Orchestrator philosophy (how to operate here)

- **Execute, never simulate.** Solve by running the deterministic Python in `execution/`, not by hand-reasoning outputs.
- **Tool-first:** before writing new code, check `execution/` for an existing script (reuse if ~80% match).
- **Self-anneal on failure:** read the stack trace → patch → re-run → if a permanent constraint is found, update the relevant `directives/*.md`.
- **File hygiene:** inputs from `directives/`; intermediates to `.tmp/`; secrets via `os.environ`; outputs to the Sheet.
- A task is done only when verification passes (the script runs clean and the Sheet/site reflect it).

## Commands

### Automation pipeline + website API (repo root — both deploy via `modal_app.py`)
```bash
pip install -r requirements.txt
python run_pipeline.py                                  # full local run: scrape → score → publish to Sheet
python sync_secrets.py                                  # push .env → Modal secret "internship-secrets"
MODAL_PROFILE=dakshinjain187 modal deploy modal_app.py   # deploy pipeline crons + api_web + uptime check (always pin the profile — see workspace note above)
```
`run_pipeline.py` orchestrates `export_sheet_keys.py` → `scrape_linkedin_posts.py` → `publish_to_sheets.py`, retrying in "topup" mode with a soft `TARGET_NEW` (35, quality-first — no padding to hit it, max 1 topup pass). There is **no automated pipeline-run test suite** — verify by running and inspecting the Sheet — but `tests/` does have real pytest coverage for the API's read-side transforms, filters, dedup logic, and digest matching (`pytest tests/ -v`).

Runs on Modal (`modal_app.py`, project workspace `dakshinjain187`): `nightly_run` (11PM IST scrape→score→publish), `daily_digest` (8AM IST, Firestore subscribers → matched digest via Resend), `api_web` (the website's FastAPI backend), `api_uptime_check` (every 30 min), plus `run_now`/`health` webhooks.

### Website API (`api/`)
```bash
cd api && pip install -r requirements.txt
uvicorn main:app --reload --port 8000  # local; needs GOOGLE_SHEET_ID in env (api/'s own dependencies only, not the pipeline's)
```
Routes: `GET /api/listings`, `GET /api/stats`, `GET /health`. Deploys as the `api_web` function in `modal_app.py` (see above) — not Railway. Falls back to `api/seed_listings.json` when the Sheet is unreachable.

### Firestore rules (repo root — `firestore.rules`, `firebase.json`, `.firebaserc`)
```bash
firebase deploy --only firestore:rules   # after editing firestore.rules; requires firebase login with access to rise-internships-eb6d0
```

### Front end (`rise-web/`)
```bash
cd rise-web && npm install
npm run dev                            # set VITE_API_BASE + VITE_FIREBASE_* in rise-web/.env (blank VITE_API_BASE = seed data)
npm run build                          # production build → dist/ (deploys to Vercel)
```
Known local quirk: if `npm run dev` fails with a `'vite' is not recognized` / path-resolution error, the `.bin` shim can go stale after installing across multiple sessions — `rm -rf node_modules && npm install` fixes it, or run `node node_modules/vite/bin/vite.js` directly.

## Architecture notes that span files

- **Pipeline scoring/filtering** lives in `execution/llm_post_analyzer.py`: an LLM extracts structured fields and sets `should_include`; posts then pass a deterministic quality gate in `execution/quality_filter.py` (scam/aggregator/WhatsApp-apply/unpaid-tech/location, single source of truth for both the scrape and analysis phases). LLM provider cascades **OpenRouter → Gemini → OpenAI → Groq → regex** based on which API key is set (`configure_llm`).
- **The Sheet schema is 18 columns A–R** (`HEADERS` in `execution/publish_to_sheets.py`; mirrored by `COL` in `api/sheets.py`). Changing columns means editing **both**. `api/sheets.py:_row_to_listing` derives `id`, `cluster`, `score`, and `hoursAgo` on read — those are computed, not stored. A second `Meta` worksheet holds the latest run's `scanned`/`rejected`/`added` counts for `/api/stats`.
- **Decoupled from ftbhustle:** the pipeline used to also POST every internship to an external `internal.ftbhustle.com` API. That `ingest_to_api()` call was removed — the Sheet is now the single source of truth. Do not reintroduce external pushes.
- **`execution/founders_*.py` (including `founders_role_filter.py`, its own separate filter — distinct from the shared `quality_filter.py` above) is a separate, personal pipeline** — Daksh's own Founder's-Office/AI-Automation/GTM job feed, publishing to a *different* Google Sheet entirely (`publish_founders_roles.py`'s `FOUNDERS_SHEET_ID`). Unrelated to Rise/`rise-web` — don't touch when working on the site or the main pipeline.
- **`rise-web/` is the active site.** `ftb-web/` (the "Dispatch" editorial design, custom CSS + GSAP) is **legacy/superseded**; `codenest/` is an unrelated video-hero experiment. Don't edit those when working on the site.
- **`rise-web` design system:** Tailwind with HSL CSS tokens in `src/index.css`, Instrument Serif (display) + Inter (body), indigo accent, frosted-glass panels, Framer Motion for entrance + scroll animations. New sections must match these tokens (never raw colors). Data flows through `src/lib/api.js` (live) with `src/lib/seed.js` fallback; apply actions go through `src/lib/format.js:openApply` (applyLink → postUrl → mailto). Sign-in state comes from `src/lib/AuthContext.jsx`'s `useAuth()`; digest preferences are written directly from `EmailAlerts.jsx` to Firestore via `src/lib/firebase.js`'s `db` export — no backend round-trip.

## Environment variables

- **Pipeline** (`.env`, also synced to Modal secret `internship-secrets`): `APIFY_API_TOKEN`, one LLM key (`OPENROUTER_API_KEY`/`GEMINI_API_KEY`/`OPENAI_API_KEY`/`GROQ_API_KEY`), `GOOGLE_SHEET_ID`, `GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`, `RESEND_API_KEY` (digest send only — Resend's contacts/audience feature is unused), `FRONTEND_ORIGIN` (CORS for `api_web`, must exactly match the Vercel origin or CORS silently breaks). `GOOGLE_API_KEY`/`RESEND_AUDIENCE_ID` are **not used anywhere** despite older docs/setup implying otherwise — don't bother setting them.
- **Digest cron only** (separate Modal secret `firebase-admin-key`, deliberately **not** part of `internship-secrets` since that bundle is also reachable by the public `run_now` webhook): `FIREBASE_SERVICE_ACCOUNT_JSON` — the full service-account JSON as one string, loaded via `firebase_admin.credentials.Certificate()` from a temp file at runtime (`tempfile.gettempdir()`, not a hardcoded path — this script also runs locally on Windows).
- **Front end** (Vercel + `rise-web/.env` for local dev): `VITE_API_BASE` = the Modal `api_web` URL; `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID` (all public by design — Firestore access is controlled by security rules, not by keeping these secret).

Note: root `.env` is read-protected in this environment — changes to `GOOGLE_SHEET_ID` etc. must be made by the user (and re-synced via `sync_secrets.py` + redeployed, since Modal containers snapshot secret values at startup and don't hot-reload). `rise-web/.env` is not similarly protected (its values are public config, not secrets).
