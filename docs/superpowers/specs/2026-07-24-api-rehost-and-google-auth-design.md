# Design: API rehost off Railway + Google Sign-In digest emails

Date: 2026-07-24
Status: Approved by user, ready for implementation planning

## Context

Two independent problems surfaced while scoping the requested email feature:

1. **Production is currently broken.** `rise-web-kappa.vercel.app` (Vercel, live, HTTP 200)
   points at `rise-api-production-a6c4.up.railway.app`, which now returns Railway's own
   `{"status":"error","code":404,"message":"Application not found"}` — the Railway
   free trial has expired. Per `rise-web/src/lib/api.js:25-36`, `fetchListings()` and
   `fetchStats()` silently fall back to hardcoded `SEED_LISTINGS`/`SEED_STATS` on any
   fetch failure, so every visitor currently sees canned sample data, not real
   internships. `subscribe()` (api.js:48-60) has no fallback and simply throws.
2. **The requested feature — automatic per-field digest emails after Google
   sign-in — needs infrastructure that doesn't exist yet:** there is no user
   database (only the Google Sheet and a Resend contacts audience) and no
   authentication of any kind (`EmailAlerts.jsx` is a plain, unauthenticated
   email-capture form).

These don't share code or infrastructure, so they are scoped as two sequential
projects. Project A is a small, urgent infra fix. Project B is the actual new
feature and depends on a manual step (creating a Firebase project) that only
the account owner can do.

### What already exists and is reused as-is

- `execution/send_daily_digest.py` — builds and sends the personalized digest
  HTML; already scheduled nightly.
- `modal_app.py` — already defines `nightly_run` (11PM IST scrape→score→publish)
  and `daily_digest` (8AM IST digest) crons on Modal, and already has a working,
  authenticated Modal CLI in this environment (profiles `dakshinjain187` /
  `fireinthebellyftb`).
- `api/sheets.py`, `execution/publish_to_sheets.py` — the 18-column Sheet schema
  (`HEADERS` / `COL`) is unchanged by this work.
- Resend — kept as the transactional send API; only its "contacts/audience"
  role is being replaced.

## Project A — Rehost `api/` off Railway onto Modal

**Goal:** the live site shows real internships again, on infrastructure already
paid for and already authenticated, with no new platform/account.

### Architecture

```
rise-web (Vercel, unchanged)
   │  VITE_API_BASE → new Modal web endpoint URL
   ▼
api/main.py served via modal.asgi_app()   ← NEW: was Railway (Procfile), now Modal
   │  (routes unchanged: /api/listings, /api/stats, /api/subscribe, /health)
   ▼
Google Sheet ("RISE Internships")   ← unchanged
```

### Components

- Add a Modal function to `modal_app.py` (or a new `modal_api.py` imported by
  it) that wraps the existing `api/main.py` FastAPI `app` object with
  `@modal.asgi_app()`. Reuse the existing `image` definition, adding
  `api/`'s dependencies (`fastapi`, `httpx`, `pydantic[email]` — check
  `api/requirements.txt` for the exact list) and `add_local_dir("api", ...)`.
- Existing env vars (`GOOGLE_SHEET_ID`, `GOOGLE_API_KEY`, `RESEND_API_KEY`,
  `FRONTEND_ORIGIN`) move from Railway's dashboard into the same
  `internship-secrets` Modal secret already used by the pipeline (one secret,
  one place, consistent with how the rest of this repo does secrets).
- No route or response-shape changes — `rise-web` needs exactly one change:
  `VITE_API_BASE` in Vercel updated to the new `*.modal.run` URL.
- Railway's `api/Procfile` becomes dead weight once this ships; leave it in
  place (harmless) rather than deleting, unless the user wants Railway fully
  decommissioned from the repo too.

### Error handling

Unchanged from today — `api/main.py`'s existing try/except → `503` fallback
patterns, and `rise-web`'s existing seed-data fallback, both stay as
defense-in-depth. The fix is that the primary path starts working again, not
a change to the fallback behavior.

### Verification

- `curl` the new Modal endpoint's `/health`, `/api/listings`, `/api/stats`
  directly and confirm real Sheet data comes back (not empty/error).
- After the Vercel env var update + redeploy, load the live site and confirm
  real listings render (not the seed-data set, which is visually
  distinguishable / a fixed small count).
- Submit the existing subscribe form once and confirm a 201 (not a network
  error) and a Resend welcome email arrives.

## Project B — Google Sign-In with per-field automatic digest emails

**Goal:** a student can sign in with Google, pick the fields/cities/grad-year
they care about, and automatically receive matching internships in their
inbox — no separate manual email-capture step.

### Why Firebase (chosen over a Sheet-based "Users" tab or a no-DB
verified-email-only approach)

The user asked for the most efficient option. Firebase Authentication does
the entire Google OAuth flow (popup, token refresh, session) in a few lines
of the official SDK — versus hand-rolling OAuth + JWT sessions. Firestore is
a real low-latency document store appropriate for per-user preference
lookups on every page load and every nightly digest run, unlike the Sheets
API (rate-limited, meant for the internship-listing dataset, not a live
per-request user store). Both are free at this scale. The trade-off, accepted
by the user, is one new external platform dependency.

### Architecture

```
rise-web (Vercel)
  │ Firebase JS SDK: "Continue with Google" → Firebase Auth (Google provider)
  │ on success, client writes users/{uid} directly to Firestore
  │   (Firestore security rule: allow write only if request.auth.uid == uid)
  ▼
Firestore: users/{uid} = { email, roles[], cities[], gradYear, remote, updatedAt }

execution/send_daily_digest.py (Modal cron, 8AM IST, unchanged schedule)
  │ fetch_contacts() → REPLACED: query all Firestore users/ docs
  │   via firebase-admin, using a service-account key held as a Modal secret
  │ match_for() → unchanged (same role/city matching logic)
  ▼
Resend "send email" API only (POST /emails) — contacts/audience API dropped
  ▼
Subscriber inbox
```

### Components

- **Firebase project** (manual, user-owned step): create project, enable
  Google as a sign-in provider, create a Web App to get the client config,
  generate a service-account key for server-side Admin SDK use. This is the
  same category of manual step as the existing `credentials.json`/
  `token.json` Google OAuth setup already in this repo.
- **`rise-web` changes:**
  - New `src/lib/firebase.js` — initializes the Firebase app from
    `VITE_FIREBASE_*` env vars.
  - New auth context/hook (`onAuthStateChanged`) so the Navbar can show
    sign-in vs. signed-in-avatar state.
  - `EmailAlerts.jsx` is replaced by a "Continue with Google" + preferences
    form; on submit, writes directly to the caller's own `users/{uid}`
    Firestore doc (no backend round-trip needed for this write, since
    Firestore security rules enforce the same-user constraint).
  - `rise-web/src/lib/api.js`'s `subscribe()` and the `/api/subscribe` backend route
    are removed once this ships, since Firestore is now the single
    preferences store — avoids running two parallel subscriber systems.
- **Backend changes:** `firebase-admin` added to the Modal image; used only
  by `send_daily_digest.py` to read all `users/` docs (Admin SDK bypasses
  Firestore security rules, appropriate for a trusted server-side cron).
  `api/main.py` itself needs no auth-token verification, since the frontend
  talks to Firestore directly rather than through a backend endpoint.
- **`execution/send_daily_digest.py` changes:** `fetch_contacts()` swapped
  for a Firestore query; `_prefs()` adjusted to Firestore's field shape
  (already-a-list, no comma-split needed); `match_for()` and `build_html()`
  unchanged.

### Error handling

- Firebase Auth failure client-side → inline error, sign-in is optional
  (doesn't gate browsing/applying to internships).
- Firestore write failure → inline error + retry, matching existing
  `EmailAlerts.jsx` status-machine pattern (`idle | loading | done | error`).
- Digest cron: Firestore fetch failure → log and skip the run entirely
  (existing `dry_run`-style safe-exit pattern in `send_daily_digest.py`);
  a single subscriber's send failure still doesn't stop the others (already
  true today).

### Verification

- Sign in on localhost with a real (test-mode) Firebase project; confirm the
  `users/{uid}` doc appears in the Firestore console with the right fields.
- Run `send_daily_digest.py` locally against that same Firestore project
  (dry run without `RESEND_API_KEY` prints the matched sample, same as
  today) and confirm the signed-in test user's saved fields/cities produce
  the expected matches.
- Deploy, then verify one real end-to-end send before trusting the 8AM
  schedule.

## Deployment sequencing

1. Ship Project A, `modal deploy` it, update Vercel's `VITE_API_BASE`,
   confirm live data — each deploy step confirmed with the user first since
   it touches shared/live infrastructure.
2. User creates the Firebase project (blocking manual step).
3. Ship Project B's code, `modal deploy` the updated pipeline/digest/image,
   confirmed with the user first.

## Out of scope / explicitly not touched

- The `founders_*` scripts (separate personal pipeline, different Google
  Sheet) — unrelated to `rise-web`, not touched by this work.
- The Sheet's 18-column schema — unchanged.
- `ftb-web/` and `codenest/` — legacy/unrelated, not touched.
