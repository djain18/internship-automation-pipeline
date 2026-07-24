# Rehost api/ off dead Railway onto Modal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live Rise website show real internship data again by moving
`api/main.py` off Railway (trial expired, returns 404 for everything) onto
Modal — the platform already running this repo's pipeline crons — with no
route or response changes, then re-point the frontend and the digest cron at
the new URL.

**Architecture:** Add one new Modal function, `api_web`, to the existing
`modal_app.py`, decorated with `@modal.asgi_app()`, serving the unmodified
`api/main.py` FastAPI `app` object. It gets its own lightweight image (not
the pipeline's heavy one) and `min_containers=1` so the public-facing site
never cold-starts. `api/main.py`'s source is untouched — the only new code
is the import glue in `modal_app.py` plus a regression test that proves that
glue actually works.

**Tech Stack:** Modal 1.3.1 (confirmed installed and authenticated, profiles
`dakshinjain187` / `fireinthebellyftb`), FastAPI 0.115.5, pytest 8.2.2
(already used by this repo's existing `tests/` suite), Vercel CLI 54.18.7
(confirmed installed and authenticated as `dakshinjain187-7460`, `rise-web/`
already linked to Vercel project `rise-web`).

This is **Project A** from
`docs/superpowers/specs/2026-07-24-api-rehost-and-google-auth-design.md`.
Project B (Google Sign-In + Firestore) is out of scope here — it's blocked
on the user creating a Firebase project first.

## Global Constraints

- Do not modify `api/main.py`, `api/sheets.py`, or `api/email_service.py` —
  the spec requires no route/response-shape changes; the fix is entirely in
  how `modal_app.py` imports and serves the existing `app` object.
- Pin the new image's dependencies to exactly what's in
  `api/requirements.txt`: `fastapi[standard]==0.115.5`,
  `uvicorn[standard]==0.32.1`, `httpx==0.27.2`, `pydantic[email]==2.10.3`,
  `python-dotenv==1.0.1`.
- Use a **dedicated** Modal image for the API function — never attach the
  pipeline's existing heavy `image` (it carries `apify-client`,
  `google-genai`, `groq`, `openai`, none of which the API needs) to `api_web`.
- Set `min_containers=1` on `api_web` so it doesn't cold-start on live
  traffic. This has a small ongoing Modal compute cost — acceptable per the
  approved spec, but call it out explicitly when reporting Task 2 done.
- `GOOGLE_API_KEY` is **not** actually read anywhere in `api/sheets.py`
  (verified: `sheets.py` fetches the Sheet via a keyless CSV export URL, not
  the Sheets API). Do not treat it as a required secret, despite CLAUDE.md's
  environment-variables section listing it — that line is stale.
- Any command that touches live/shared infrastructure (`modal deploy`,
  `vercel env add`, `vercel --prod`) must be confirmed with the user
  immediately before running it, individually, not batched — this was an
  explicit standing agreement for this work, not a one-time approval.
- `.env` is read-protected in this environment — any step that requires
  adding a value to `.env` must be handed to the user to perform themselves;
  do not attempt to read or write it.
- If deploying to Modal hits a blocker deeper than the known import-path fix
  in this plan, the documented fallback is redeploying the existing,
  unmodified `api/Procfile` to Render or Fly's free tier — stop and raise it
  rather than continuing to debug Modal under time pressure.

---

### Task 1: Regression test for the api/main.py import-path assumption

This codifies the bug an independent reviewer found in the first draft of
the design spec: `api/main.py:26-27` does bare imports
(`from sheets import fetch_listings, fetch_stats`, `import email_service`)
that only resolve when `api/` is on `sys.path` — true on Railway only
because `uvicorn main:app` runs with `api/` as the cwd. The Modal wrapper
(Task 2) relies on inserting `/app/api` onto `sys.path` before importing
`main` — this test proves that exact mechanism works, using the same
sys.path-insertion pattern this repo's existing `tests/conftest.py` already
uses for `api/`.

**Files:**
- Create: `tests/test_main_asgi_import.py`
- Reference (do not modify): `tests/conftest.py` (already puts `api/` on
  `sys.path` for every test in this directory), `api/main.py`

**Interfaces:**
- Consumes: `main.app` (the FastAPI instance created in `api/main.py`) via
  plain `import main`, exactly as `tests/test_sheets.py` already does
  `import sheets`.
- Produces: nothing consumed by later tasks — this is a standalone
  regression test.

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_asgi_import.py`:

```python
"""Regression test: api/main.py must import cleanly and serve correctly when
api/ is on sys.path but is NOT the current working directory. This is
exactly how modal_app.py's api_web() function loads it (see Task 2) — this
assumption broke silently once already during design review, so it's
pinned here.
"""
from fastapi.testclient import TestClient

import main


def test_main_app_imports_and_serves_health():
    client = TestClient(main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_main_app_has_expected_routes():
    paths = {route.path for route in main.app.routes}
    assert "/api/listings" in paths
    assert "/api/stats" in paths
    assert "/api/subscribe" in paths
    assert "/health" in paths
```

Note: this test should actually **pass immediately** once written, since
`tests/conftest.py` already inserts `api/` onto `sys.path` for the whole
`tests/` directory and `api/main.py` itself needs no code changes. That's
the point — Step 2 confirms this is genuinely already true today, not an
assumption.

- [ ] **Step 2: Run the test and confirm it passes**

Run: `pytest tests/test_main_asgi_import.py -v`
Expected: both tests PASS. If either fails, stop — it means the import
assumption Task 2 is about to rely on is not actually true, and Task 2's
approach needs rethinking before writing any Modal code.

- [ ] **Step 3: Run the full existing test suite to confirm nothing else broke**

Run: `pytest tests/ -v`
Expected: all tests pass (this repo's existing `test_filters.py`,
`test_publish_dedup.py`, `test_scrape_extract.py`, `test_sheets.py`, plus
the new file).

- [ ] **Step 4: Commit**

```bash
git add tests/test_main_asgi_import.py
git commit -m "test: pin the sys.path assumption the Modal API wrapper will rely on"
```

---

### Task 2: Add a dedicated lightweight image + ASGI web function to modal_app.py

**Files:**
- Modify: `modal_app.py` (append new image + function; do not touch existing
  `image`, `run_pipeline`, `nightly_run`, `daily_digest`, `run_now`, `health`,
  `test_log` functions)

**Interfaces:**
- Consumes: `api/main.py`'s `app` object (via the sys.path mechanism proven
  in Task 1), the existing `modal.Secret.from_name("internship-secrets")`.
- Produces: a new Modal function named `api_web`, deployed under the same
  `app = modal.App("internship-pipeline")`. Its live URL follows Modal's
  standard pattern and is printed by `modal deploy` — Task 3 captures it.

- [ ] **Step 1: Add the dedicated image definition**

In `modal_app.py`, after the existing `image = (...)` block (currently ending
around line 46), add:

```python
# ── Lightweight image for the website API — deliberately NOT the pipeline's
# heavy image (apify-client, google-genai, groq, openai etc. are not needed
# here and would add cold-start weight to a public-facing endpoint). ──
api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]==0.115.5",
        "uvicorn[standard]==0.32.1",
        "httpx==0.27.2",
        "pydantic[email]==2.10.3",
        "python-dotenv==1.0.1",
    )
    .add_local_dir("api", remote_path="/app/api")
)
```

- [ ] **Step 2: Add the ASGI web function**

In `modal_app.py`, after the existing `health()` function, add:

```python
# ── Website API — replaces the now-dead Railway deployment ──────
@app.function(
    image=api_image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
    ],
    min_containers=1,  # keep one warm — this is public-facing, no cold starts
)
@modal.asgi_app()
def api_web():
    """Serves api/main.py's FastAPI app. Imports it lazily, after putting
    api/ on sys.path, because main.py's own top-level imports
    (`from sheets import ...`, `import email_service`) only resolve that way
    — see tests/test_main_asgi_import.py for the pinned assumption."""
    import sys
    if "/app/api" not in sys.path:
        sys.path.insert(0, "/app/api")
    from main import app as fastapi_app
    return fastapi_app
```

- [ ] **Step 3: Verify the file parses and the existing functions are untouched**

Run: `python -c "import ast; ast.parse(open('modal_app.py').read())"`
Expected: no output (no `SyntaxError`).

Run: `git diff modal_app.py`
Expected: only additions (the `api_image` block and the `api_web` function)
— no lines removed or changed inside `run_pipeline`, `nightly_run`,
`daily_digest`, `run_now`, `health`, or `test_log`.

- [ ] **Step 4: Commit**

```bash
git add modal_app.py
git commit -m "feat: add Modal ASGI function to serve api/ (replaces dead Railway deploy)"
```

---

### Task 3: Add the missing secrets and deploy `api_web`

The pipeline's `.env` (synced to Modal's `internship-secrets` secret via
`sync_secrets.py`) currently holds pipeline-only values
(`APIFY_API_TOKEN`, an LLM key, `GOOGLE_SHEET_ID`, `GOOGLE_CREDENTIALS_JSON`,
`GOOGLE_TOKEN_JSON`). Per CLAUDE.md, `RESEND_API_KEY`, `RESEND_AUDIENCE_ID`,
and `FRONTEND_ORIGIN` were configured directly in Railway's dashboard, not in
this shared `.env` — so they are very likely missing from the Modal secret
today and must be added before `api_web` will work correctly.

**Files:**
- User-edited (read-protected for the agent): root `.env`
- Reference only: `sync_secrets.py`, `api/main.py` (reads `FRONTEND_ORIGIN`),
  `api/email_service.py` (reads `RESEND_API_KEY`, `RESEND_AUDIENCE_ID`,
  `FROM_EMAIL`)

**Interfaces:**
- Consumes: Task 2's `api_web` function definition.
- Produces: a live `https://*.modal.run` URL for `api_web`, which Tasks 4
  and 5 point at.

- [ ] **Step 1 (user action, cannot be automated): confirm `.env` has the API's secrets**

Ask the user to open the root `.env` and confirm it contains (adding any
that are missing):

```
RESEND_API_KEY=<same value currently set in Railway's dashboard>
RESEND_AUDIENCE_ID=<same value currently set in Railway's dashboard>
FRONTEND_ORIGIN=<the exact Vercel production URL, e.g. https://rise-web-kappa.vercel.app>
```

`FROM_EMAIL` is optional (code defaults to `onboarding@resend.dev` if unset).
Do **not** add `GOOGLE_API_KEY` — it's unused (see Global Constraints).

- [ ] **Step 2: Re-sync the Modal secret**

Confirm with the user before running (this overwrites the live
`internship-secrets` Modal secret):

Run: `python sync_secrets.py`
Expected: `[OK] Successfully synced secrets to Modal via CLI!` and a count
that includes the newly added keys.

- [ ] **Step 3: Deploy**

Confirm with the user before running (this is a live infrastructure change):

Run: `modal deploy modal_app.py`
Expected: deploy succeeds and prints a URL for `api_web`, formatted like
`https://<workspace>--internship-pipeline-api-web.modal.run`. **Copy this
exact URL** — later tasks need it verbatim.

- [ ] **Step 4: Verify the deployed endpoint directly**

Run (substituting the real URL from Step 3):
```bash
curl -s https://<the-url>/health
curl -s https://<the-url>/api/listings | head -c 300
curl -s https://<the-url>/api/stats
```
Expected: `/health` returns `{"ok":true}`; `/api/listings` returns a JSON
array of real listing objects (not Railway's `{"status":"error",...}` shape,
not an empty `[]`); `/api/stats` returns a JSON object with numeric fields.

If `/api/listings` comes back empty, do not proceed to Task 4 — it means
either `GOOGLE_SHEET_ID` didn't make it into the secret, or the Sheet's
CSV-export permission ("anyone with the link can view") isn't set; diagnose
before continuing.

- [ ] **Step 5: No commit for this task** — it's operational (secrets +
deploy), not a code change. Record the confirmed live URL in the PR/commit
message of Task 4 instead, since that's where it's first written into code.

---

### Task 4: Point `send_daily_digest.py`'s `API_BASE` at the new URL

`execution/send_daily_digest.py:35` currently hardcodes the dead Railway URL
as its own default for `API_BASE` — a variable entirely separate from
`rise-web`'s `VITE_API_BASE`. This was the specific bug an independent
reviewer flagged: fixing only the frontend's env var would leave the 8AM
digest cron silently fetching `[]` listings and sending nothing, forever,
with no visible error.

**Files:**
- Modify: `execution/send_daily_digest.py:35`

**Interfaces:**
- Consumes: the live URL confirmed working in Task 3, Step 4.
- Produces: `send_daily_digest.py` fetching real listings when run (locally
  or by its existing Modal cron schedule) — no other function signatures
  change.

- [ ] **Step 1: Update the default**

In `execution/send_daily_digest.py`, change line 35 from:

```python
API_BASE   = os.getenv("API_BASE", "https://rise-api-production-a6c4.up.railway.app").rstrip("/")
```

to (substituting the real URL confirmed in Task 3):

```python
API_BASE   = os.getenv("API_BASE", "https://<the-url-from-task-3>").rstrip("/")
```

- [ ] **Step 2: Verify locally**

Run: `python execution/send_daily_digest.py`
Expected: log line `Fetched N live listings` where `N > 0` (not the
`No listings — nothing to send.` warning path). Since `RESEND_API_KEY` is
present locally only if the user's `.env` has it, this will likely also log
a `DRY RUN` sample digest — that's fine and expected; the thing being
verified here is the listings fetch count, not an actual send.

- [ ] **Step 3: Commit**

```bash
git add execution/send_daily_digest.py
git commit -m "fix: point digest cron's API_BASE at the new Modal-hosted API

Railway's trial expired; api/ was rehosted onto Modal (see modal_app.py's
api_web function). This was the second of two places the old dead Railway
URL was hardcoded — rise-web's VITE_API_BASE is the other, fixed in the
next task."
```

---

### Task 5: Point `rise-web`'s `VITE_API_BASE` at the new URL and redeploy

**Files:**
- No repo files change — this is a Vercel project environment variable,
  managed via the Vercel CLI (already authenticated as `dakshinjain187-7460`,
  `rise-web/` already linked to Vercel project `rise-web` per
  `rise-web/.vercel/project.json`).

**Interfaces:**
- Consumes: the live URL confirmed working in Task 3, Step 4.
- Produces: the production Vercel deployment of `rise-web` serving real
  listings instead of `SEED_LISTINGS`/`SEED_STATS`
  (`rise-web/src/lib/api.js:25-46`).

- [ ] **Step 1: Check the current value (if any)**

Run (from `rise-web/`): `vercel env ls production`
Expected: shows whether `VITE_API_BASE` already exists for the production
environment (it may currently hold the dead Railway URL, or be unset if
Vercel's build fell back to blank).

- [ ] **Step 2: Set the new value**

Confirm with the user before running (this changes a live, shared Vercel
project's config):

Run (from `rise-web/`):
```bash
vercel env rm VITE_API_BASE production --yes
vercel env add VITE_API_BASE production
```
When prompted for the value, paste the exact URL confirmed in Task 3,
Step 4 (no trailing slash).

- [ ] **Step 3: Redeploy production so the build picks up the new env var**

Confirm with the user before running:

Run (from `rise-web/`): `vercel --prod`
Expected: build succeeds, prints the production URL
(`rise-web-kappa.vercel.app` or current custom domain).

- [ ] **Step 4: Verify the live site**

Load the production URL in a browser (or `curl` it and inspect the initial
HTML/API calls via devtools if a full browser check isn't available) and
confirm the listings shown are the real, larger, varied set from the Sheet
— not `SEED_LISTINGS`' small fixed sample (check `rise-web/src/lib/seed.js`
for its exact contents to know what "still seed data" would look like).

Also submit the site's subscribe form once with a throwaway email and
confirm it returns success (HTTP 201 under devtools' Network tab, or via
`curl -X POST <the-url>/api/subscribe -H "Content-Type: application/json" -d '{"email":"test@example.com"}'`)
rather than a network error — this exercises `/api/subscribe`, which the
old dead Railway URL could never reach at all.

- [ ] **Step 5: No commit needed** — purely a hosted-environment config
change, already captured in this task's description for anyone auditing
what changed and why.

---

### Task 6 (optional — do only if the user wants it before moving to Project B): lightweight uptime check

This is the one nice-to-have from the design spec worth doing now rather
than deferring indefinitely: the *entire reason* this project exists is that
an outage went unnoticed for an unknown period, because the seed-data
fallback made the site look fine. A cheap scheduled check closes that gap
without adding any new external alerting service.

**Files:**
- Modify: `modal_app.py` (append one more scheduled function)

**Interfaces:**
- Consumes: the confirmed live URL from Task 3.
- Produces: a Modal-scheduled function, `api_uptime_check`, visible in
  Modal's own dashboard/logs — no other code depends on it.

- [ ] **Step 1: Add the scheduled check**

In `modal_app.py`, after `api_web`, add (substituting the real URL):

```python
# ── Cheap uptime check — the whole reason this project exists is that the
# last outage went unnoticed because seed-data masked it. ──────────
@app.function(
    image=api_image,
    schedule=modal.Period(minutes=30),
)
def api_uptime_check():
    import requests
    url = "https://<the-url-from-task-3>/api/listings"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        count = len(data) if isinstance(data, list) else 0
        if count == 0:
            print(f"⚠️  UPTIME CHECK: {url} returned 0 listings")
        else:
            print(f"✅ UPTIME CHECK: {url} returned {count} listings")
    except Exception as e:
        print(f"❌ UPTIME CHECK FAILED: {url} — {e}")
```

- [ ] **Step 2: Deploy**

Confirm with the user before running: `modal deploy modal_app.py`

- [ ] **Step 3: Verify**

Run: `modal run modal_app.py::api_uptime_check`
Expected: prints `✅ UPTIME CHECK: ... returned N listings` with `N > 0`.

- [ ] **Step 4: Commit**

```bash
git add modal_app.py
git commit -m "feat: add a 30-min scheduled uptime check for the rehosted API"
```

---

## Definition of done for this plan

- `pytest tests/ -v` passes in full, including the new
  `test_main_asgi_import.py`.
- `modal deploy modal_app.py` has been run and `api_web`'s URL responds with
  real Sheet data on `/health`, `/api/listings`, `/api/stats`.
- `execution/send_daily_digest.py`'s `API_BASE` points at that same URL and
  a local run logs a non-zero fetched-listings count.
- `rise-web`'s production Vercel deployment has `VITE_API_BASE` set to that
  URL and the live site visibly shows real (non-seed) listings.
- The subscribe form on the live site succeeds end-to-end.
