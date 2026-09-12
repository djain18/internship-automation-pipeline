# Rise Private Internship Hunt Integration

Status: approved for implementation on 2026-09-10.

## Architecture

The personal hunt runs from this repository but remains isolated from the
public Rise pipeline. Policy-neutral utilities live in `execution/hunt_core`;
the private policy and orchestration live in `personal_hunt`. The existing
public Sheet schema, filters, website listings, and Resend subscriber digest do
not change.

The private Modal deployment retains app name `daksh-internship-hunt`, volume
`internship-hunt-data`, and one combined cron. The 00:30 branch collects after
the public Rise 23:00 run. The 08:00 branch reads only a pointer-validated live
run and sends only previously unemailed Kimi-approved matches.

## Processing contract

1. Fetch the Rise live Sheet without seed fallback, then the configured FTB,
   YC, Wellfound, WWR, harvested ATS boards, portfolio, human-import,
   Daksh-spotted, and funding sources. Wellfound stays enabled per Daksh's
   override despite zero yield so far; its records die before any LLM cost.
2. Normalize with stable first discovery, ten-day internship freshness, and
   dated 15/30-day funding windows.
3. Apply deterministic hard exclusions, deduplication, scoring, and balanced
   Bengaluru/remote selection.
4. Invoke the approved public-post LinkedIn actor on every scheduled run with
   a $0.70 run cap and a $25 aggregate monthly hard stop shared across rotation
   keys. Rotate `APIFY_TOKEN_1`..`APIFY_TOKEN_7` with per-slot usage checks;
   all-unusable fails closed. A manual token change does not reset the ledger.
5. Require Kimi K2.5 fit >=70, relevant=true, spam=false for digest admission;
   malformed/model-failed batches fail closed for email.
6. Validate application links. Definitive 404/410 is rejected; temporary or
   access failures are retained with a manual-verification warning.
7. Generate evidence, funding problem hypotheses, resume routing, artifacts,
   and manual-only outreach drafts.
8. Atomically write the run and latest-live pointer, then update the eight-tab
   Sheet without overwriting human-owned values.

## Private interfaces

`GET /api/personal/latest` requires a Firebase bearer ID token. Missing or
invalid tokens return 401; a verified email other than
`dakshinjain187@gmail.com` or `dakshjainn02@gmail.com` returns 403;
missing/unusable live artifacts return
404/503. Successful responses are sanitized, use exact-origin CORS, and set
`Cache-Control: no-store`.

The lazy `/my-hunt` page is noindex and read-only. It displays latest run
status, Bengaluru and remote matches, evidence, recommended resume, copyable
drafts, funding/problem signals, source health, integration state, and Apify
spend. It has explicit loading, empty, stale, error, and access-denied states.

## Delivery and safety

Gmail sends multipart plain-text plus Rise-branded HTML. Delivery requires the
approved recipient, a usable live run, and the separate enable flag.

**Amended 2026-09-12** (2026-09-12 incident: the whole email was silently
suppressed whenever the day's only match had already been sent on a prior
day, discarding the verification tray and funding sections along with it,
with no error and no signal): delivery no longer requires at least one
newly approved opportunity. A day with nothing new still sends, with the
subject and body saying so plainly — silence must mean the pipeline
broke, never "nothing to report." The delivery ledger key is the IST
calendar date plus run_id (`<ist-date>:<run_id>`), not run_id alone, so a
retry within the same IST morning stays idempotent while a genuinely new
day always sends even against the same run artifact; a bare run_id key
recorded before this change still counts as already-sent. The ledger
stores the Gmail message ID and sent opportunity IDs only after success,
same as before. A collect older than 18 hours is flagged stale in the
subject and body rather than silently re-rendered as fresh, and the
`--digest-latest` delivery path now catches its own exceptions and
best-effort emails a failure note before re-raising.

The LinkedIn field-extraction repair step (posts arrive as text without
structured company/title) is capped by
`config/scoring.yml:max_linkedin_extractions_per_run` (100), not a
hardcoded limit, and runs in chunked batches so one oversized prompt
cannot truncate the whole attempt; a failed batch no longer sinks the
rest. Post text is repaired for UTF-8-decoded-as-cp1252 mojibake before
the extraction validator sees it.

Local college-Wi-Fi support uses the Windows system CA through Node
`--use-system-ca` and Python `truststore`; certificate verification is never
disabled.

## Same-day gate

The implementation must pass all Python tests, Ruff, compileall, frontend tests
and production build; inspect fixture and live dry-run output; validate the
Sheet sandbox; prove API 401/403/200 behavior; inspect desktop/mobile email;
and complete one authorized canary before enabling the 08:00 schedule.
