# Design: API rehost off Railway + Google Sign-In digest emails

Date: 2026-07-24
Status: Revised after independent critique (see Revision Log). Ready for
implementation planning.

## Revision Log

An independent Sonnet reviewer read this spec plus the actual code it
references and found five must-fix issues and several nice-to-haves. All are
addressed below; the changed sections are: Project A's Components/Error
handling/Verification, and Project B's Components/Error handling. A new
"Why Modal, and not just paying Railway or moving to Render/Fly" subsection
was added to Project A to close the one place this spec had less rigor than
Project B. Summary of what changed:

1. **Import-path bug** — `api/main.py`'s bare imports only resolve when
   `api/` is the cwd. Fixed by specifying the wrapper imports the app lazily,
   inside the function, after adjusting `sys.path`.
2. **Digest cron would silently no-op** — `send_daily_digest.py`'s own
   `API_BASE` default is a *second*, separate pointer at the dead Railway URL
   that the original spec never updated. Now explicit in Project A's scope.
3. **Secret over-scoping** — the Firebase Admin key must not join the
   `internship-secrets` bundle already reachable by the public `run_now`
   webhook. Now a dedicated secret, attached only to `daily_digest`.
4. **No fault isolation in the digest loop** — one malformed Firestore doc
   would previously kill the whole run. Now per-user try/except, plus a
   Firestore rule with schema/type validation, not just a `uid` check.
5. **No migration plan for existing Resend subscribers** — now explicit.

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

### Why Modal, not paying for Railway or moving to Render/Fly

The user has already ruled out staying on Railway ("Railway has a problem...
we have to move to another platform"), so a $5/month Hobby-tier restore is
off the table regardless of its speed advantage. Between Modal and a
Render/Fly-style redeploy of the unmodified `Procfile`: Render/Fly would
require *zero* code changes and sidesteps the import-path issue below
entirely, which is a genuine speed and risk advantage for an "urgent" fix.
Modal is chosen anyway because it avoids introducing a *third* platform
(Vercel + Render/Fly + Modal-for-the-pipeline, three dashboards/accounts to
maintain, vs. Vercel + Modal, two) and reuses secrets/auth already set up
here. This is accepted as the right trade — one extra afternoon of import-path
and image-size work, in exchange for one fewer platform to operate long-term.
If the import-path fix below turns out to be more involved than expected
during implementation, Render/Fly redeploy is the fallback, not further Modal
debugging.

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
  `@modal.asgi_app()`. **Import mechanics matter and were wrong in the first
  draft of this spec:** `api/main.py:26-27` does bare imports
  (`from sheets import ...`, `import email_service`) that only resolve when
  `api/` is on `sys.path`/is the cwd — true on Railway only because
  `uvicorn main:app` runs from inside `api/`. The Modal wrapper function must
  import the app *lazily, inside the function body*, after
  `sys.path.insert(0, "/app/api")` (or running from that cwd) — not as a
  module-level `from api.main import app` in `modal_app.py`, which would
  either fail to import at all or accidentally depend on the dev machine's
  local environment happening to have `api/`'s deps installed.
- **Use a dedicated, lightweight image for this function — do not reuse the
  pipeline's image.** The pipeline's image carries `apify-client`,
  `google-genai`, `groq`, `openai`, `google-api-python-client`, etc. — none of
  which the API needs. Cold-starting all of that on every scale-to-zero
  request adds real, visitor-facing latency to the exact thing this project
  is trying to make feel live again. Build a separate `api_image` with only
  `api/requirements.txt`'s deps (`fastapi[standard]` pinned to the same
  `0.115.5` already pinned there, `httpx`, `pydantic[email]`, `google-api-python-client`
  for `sheets.py`), and set `min_containers=1` (or Modal's current equivalent
  keep-warm setting) on the web function so the public-facing API doesn't
  cold-start at all during normal traffic.
- Existing env vars (`GOOGLE_SHEET_ID`, `GOOGLE_API_KEY`, `RESEND_API_KEY`,
  `FRONTEND_ORIGIN`) move from Railway's dashboard into the same
  `internship-secrets` Modal secret already used by the pipeline (one secret,
  one place, consistent with how the rest of this repo does secrets) — this
  is fine for these values since they're not credentials that grant broad
  data access on their own (contrast with Project B's Firebase Admin key,
  which is scoped separately — see below).
- **Add a new `API_BASE` value pointing at the new Modal URL**, and update
  `execution/send_daily_digest.py`'s `API_BASE` (currently hardcoded to the
  dead Railway URL as its own independent default, `send_daily_digest.py:35`
  — a different variable from `rise-web`'s `VITE_API_BASE`, easy to miss).
  Set it via the same `internship-secrets` Modal secret (or the script's env)
  so the digest cron doesn't keep silently fetching `[]` listings forever.
- No route or response-shape changes — `rise-web` needs exactly one change:
  `VITE_API_BASE` in Vercel updated to the new `*.modal.run` URL.
- Railway's `api/Procfile` becomes dead weight once this ships; leave it in
  place (harmless) rather than deleting, unless the user wants Railway fully
  decommissioned from the repo too.

### Error handling

Unchanged from today — `api/main.py`'s existing try/except → `503` fallback
patterns, and `rise-web`'s existing seed-data fallback, both stay as
defense-in-depth. The fix is that the primary path starts working again, not
a change to the fallback behavior. One addition: because this same seed-data
fallback is what's been *masking* the current outage from view, add a
trivial uptime check (even a free external pinger against `/health`, or a
scheduled Modal function that curls `/api/listings` and alerts on empty/error)
so a future outage doesn't again go unnoticed for an unknown period.

### Rollback plan

Nothing is cut over until verified: `VITE_API_BASE` (Vercel) is only
repointed after the new Modal endpoint is curled directly and confirmed
returning real data (see Verification below). If the Modal deploy has
problems beyond a quick fix, the fallback is redeploying the existing,
unmodified `api/Procfile` to Render or Fly's free tier instead — zero code
changes needed there, since it doesn't hit the asgi-wrapper import issue at
all — rather than continuing to debug Modal under time pressure.

### Verification

- `curl` the new Modal endpoint's `/health`, `/api/listings`, `/api/stats`
  directly and confirm real Sheet data comes back (not empty/error).
- After the Vercel env var update + redeploy, load the live site and confirm
  real listings render (not the seed-data set, which is visually
  distinguishable / a fixed small count).
- Submit the existing subscribe form once and confirm a 201 (not a network
  error) and a Resend welcome email arrives.
- Run `execution/send_daily_digest.py` locally with the new `API_BASE` and
  confirm it logs a non-zero fetched-listings count (catches the exact bug
  found in review, where the digest cron would otherwise keep pointing at
  the dead Railway URL and silently send nothing every morning).

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
  │   (Firestore rule: uid match AND schema/type validation — see below)
  ▼
Firestore: users/{uid} = { email, roles[], cities[], gradYear, remote, updatedAt }

execution/send_daily_digest.py (Modal cron, 8AM IST, unchanged schedule)
  │ fetch_contacts() → REPLACED: query all Firestore users/ docs
  │   via firebase-admin, using a service-account key held in its OWN
  │   dedicated Modal secret (NOT internship-secrets — see Components)
  │ per-user loop now has try/except isolation (see Error handling)
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
- **Firestore security rule must validate schema, not just ownership.** A
  bare `allow write: if request.auth.uid == uid` lets a signed-in client
  write any shape/size of data to their own doc — and since the digest cron
  reads every doc, a malformed one previously could have broken the whole
  run (see Error handling). The rule must also check:
  `request.resource.data.keys().hasOnly(['email','roles','cities','gradYear','remote','updatedAt'])`,
  that `roles`/`cities` are lists (`is list`) with a capped length (e.g. `<= 20`
  entries), and that `email`/`gradYear` are strings under a reasonable length.
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
    **Trade-off, explicitly noted:** this removes the zero-friction,
    no-Google-account signup path entirely — a student who doesn't want to
    grant Google access can no longer get digest emails at all. Accepted
    because per-field automatic emails *from* a Google sign-in is the
    literal feature requested, not an add-on to the old form.
- **Backend changes:** `firebase-admin` added to a dedicated, lightweight
  digest-only image (not the pipeline's heavy image, for the same
  cold-start reason as Project A — though `daily_digest` runs on a schedule
  rather than serving live traffic, so this is a smaller concern than in
  Project A, more about keeping images single-purpose); used only by
  `send_daily_digest.py` to read all `users/` docs (Admin SDK bypasses
  Firestore security rules, appropriate for a trusted server-side cron).
  **The service-account key gets its own Modal secret** (e.g.
  `firebase-admin-key`), attached only to the `daily_digest` function — NOT
  folded into `internship-secrets`, which is also attached to `run_now`, a
  public unauthenticated webhook (`modal_app.py:171-183`). Folding it in
  would let that endpoint's execution context reach a credential capable of
  reading/writing every user's data; keeping it separate limits blast radius
  to the one function that actually needs it. At runtime, write the secret's
  JSON string to a temp file and load it with
  `firebase_admin.credentials.Certificate(path)` — do not bake it into the
  image the way `token.json` currently is (`modal_app.py:45`), since that
  pattern is meant for non-secret-rotatable files, not credentials.
  `api/main.py` itself needs no auth-token verification, since the frontend
  talks to Firestore directly rather than through a backend endpoint.
- **`execution/send_daily_digest.py` changes:** `fetch_contacts()` swapped
  for a Firestore query; `_prefs()` adjusted to Firestore's field shape
  (already-a-list, no comma-split needed); `match_for()` and `build_html()`
  unchanged.
- **Migration of existing Resend subscribers.** Anyone who already signed up
  via the live `EmailAlerts.jsx` form exists only in Resend's contacts list
  today and would otherwise silently stop receiving digests the moment
  `fetch_contacts()` is replaced. Before removing the Resend-contacts code
  path: pull the current contact list once, and send those addresses a
  one-time Resend email explaining the upgrade and linking to the new
  Google Sign-In flow, so real people get a chance to opt back in rather
  than being dropped without notice. Do not attempt to auto-create Firestore
  docs for them under a synthetic ID — that would create an "account" they
  never consented to and never signed into.

### Error handling

- Firebase Auth failure client-side → inline error, sign-in is optional
  (doesn't gate browsing/applying to internships).
- Firestore write failure → inline error + retry, matching existing
  `EmailAlerts.jsx` status-machine pattern (`idle | loading | done | error`).
- Digest cron: Firestore fetch failure (the whole query failing) → log and
  skip the run entirely (existing `dry_run`-style safe-exit pattern in
  `send_daily_digest.py`). **Separately, and this was missing from the first
  draft:** the per-subscriber loop in `main()` (`send_daily_digest.py:184-193`)
  currently has no exception handling around `match_for()`/`send()` for an
  individual contact. Once Firestore docs are client-writable (even with
  rule validation, e.g. an old doc shape or a rule edge case), one bad
  record must not be allowed to throw and kill every subscriber after it in
  the loop — wrap each iteration's body in its own try/except, log the
  offending doc's ID, and continue to the next subscriber.

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

1. Ship Project A, `modal deploy` it, update Vercel's `VITE_API_BASE` and
   the digest cron's `API_BASE`, confirm live data — each deploy step
   confirmed with the user first since it touches shared/live infrastructure.
2. User creates the Firebase project (blocking manual step).
3. Ship Project B's code, `modal deploy` the updated pipeline/digest/image,
   confirmed with the user first.
4. Once Project B ships, update CLAUDE.md's architecture section — its
   current claim that "the Sheet is the only coupling between the two
   systems" becomes false the moment Firestore is added as a second point
   where `rise-web` and the pipeline-side digest cron share state. This
   follows the repo's own stated "self-anneal" convention of updating
   `directives`/architecture docs when a permanent constraint changes.

## Out of scope / explicitly not touched

- The `founders_*` scripts (separate personal pipeline, different Google
  Sheet) — unrelated to `rise-web`, not touched by this work.
- The Sheet's 18-column schema — unchanged.
- `ftb-web/` and `codenest/` — legacy/unrelated, not touched.
