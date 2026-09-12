# Review notes: personal internship-hunt pipeline

## 2026-09-12 — digest silent no-send + LinkedIn extraction cap

**Trigger:** no digest email at 08:30 IST on 2026-09-12.

**Root cause A — whole email suppressed on a "nothing new" day.**
`_send_once()` in `personal_hunt/execution/pipeline.py` filtered
already-sent opportunity IDs, found nothing left, and returned
`digest_skipped_no_new_matches` — sending nothing, including the
verification tray and funding sections, which don't depend on that
filter. No error, no signal; indistinguishable from a dead pipeline.

**Root cause B — 465 records in, 2 eligible out; LinkedIn yielded zero.**
The Apify actor (`harvestapi/linkedin-post-search`) returns post text
without structured company/title, so 99 of 100 posts were rejected for
`missing_required_identity_or_source`. The existing LLM repair step
(`extract_linkedin_hiring_fields`) was hardcoded to attempt only 10 posts
per run, while 76 of the 99 met its own candidate predicate that day — a
same-day exact-match Founder's Office post (Auraaison) was discarded
purely for want of a parse. A second defect in the same path: post text
arrived mojibaked (UTF-8 decoded as cp1252), breaking the extraction
validator's exact-quote match.

**Fix, approved plan:**
`C:\Users\daksh\.claude\plans\i-want-you-to-ethereal-sloth.md`.

- A quiet day still sends mail (subject and body say so explicitly);
  delivery is keyed on the IST calendar date, not only run_id, with a
  fallback to the three pre-existing bare-run-id ledger keys so nothing
  already sent gets resent; the `--digest-latest` path now catches its
  own exceptions and best-effort emails a failure note before
  re-raising; a collect older than 18 hours is flagged stale in the
  subject and body rather than silently re-rendered as fresh; the
  00:30 IST collect's run date now uses `Asia/Kolkata`, not
  `date.today()` inside the UTC container (previously filed under the
  wrong day).
- The LinkedIn extraction cap moved from a hardcoded
  `LINKEDIN_EXTRACTION_LIMIT = 10` to
  `config/scoring.yml:max_linkedin_extractions_per_run` (100), chunked
  into 10-post batches so one oversized prompt can't truncate the whole
  batch; a failed batch no longer sinks the rest. The mojibake repair
  (`_repair_mojibake`) runs at ingest in `apify_sources.py` before the
  extraction validator sees the text. The digest now reports zero-yield
  sources with their dominant rejection reason, and reports
  `skipped_over_cap` for both LinkedIn extraction and Tier 2
  cross-functional judging so the next binding cap is visible without
  downloading an artifact.
- One apparent discrepancy (extraction reported 5 resolved on 2026-09-12,
  only 1 visible with a company in `all_scored`) was investigated and is
  **not a bug**: `deduplicate()` correctly collapses the same LinkedIn
  post fetched under multiple overlapping search queries before it
  reaches `all_scored`.

**Verified against a real cloud run**, not a fixture — Modal app
`daksh-internship-hunt`, run `run_68ef99cddd201852`, completed
2026-09-12T06:08:18Z:

| Metric | 2026-09-12 baseline (`run_52adcae3873befac`) | This run |
|---|---:|---:|
| `linkedin_posts_apify` missing-identity | 99 / 100 | 79 / 99 |
| extraction candidates / attempted / resolved | n/a / 10 / 5 | 118 / 100 / 37 |
| `eligible_count` | 2 | **5** |
| `digest_primary` | 1 (Ethereal Labs) | 3 (Auraaison, ZetaRecruiter, Ressl AI) |

Auraaison — Founder's Office Intern, posted 2026-09-11, the exact post
named in the plan as dropped for want of a parse — is now resolved,
eligible, Kimi-approved at fit 92, and in `digest_primary`.

One real self-digest was sent to `dakshinjain187@gmail.com`, Gmail
message id `1a0943cb85159dbd`, carrying 2 genuinely new matches
(Auraaison, ZetaRecruiter — Ressl AI correctly excluded as already sent
2026-09-11). Immediate replay returned the same message id with no
second send, confirming the new IST-dated ledger key is idempotent.
Sheets wrote Companies 54, Opportunities 5, Outreach 5, Artifacts 5, Runs
1, Source Health 19, Funding Signals 3 — `integrations.sheets.status:
"ok"`.

Local gates: 163 personal_hunt tests, 200 Rise tests (run as separate
commands — both suites expose a top-level `sheets` module), Ruff clean.

**Known limits, unchanged by this work:**

- Wellfound and WWR still yield zero eligible internships — both are
  remote/full-time boards behind a bot control (403 / anonymous 303) that
  is not bypassed. Now reported in the digest instead of silently absent.
- The `ftb_internships` records behind `lnkd.in` links stay rejected;
  the sole-reason verification tray still surfaces only the ones worth a
  manual look.
- Three of ten LinkedIn extraction batches failed this run (two on a
  quote-subset mismatch, one on JSON truncation at `max_tokens=3500`
  with a 10-post batch) — contained to those batches rather than sinking
  the whole extraction, but still worth a smaller batch size or higher
  `max_tokens` if `unresolved` stays high on future runs.
- The next real 08:30 IST cron (2026-09-13) has not yet been observed;
  confirm it delivers unaided and record that run's numbers here.

## 2026-09-12 — personal-hunt-migration merged to main, /my-hunt deployed

`personal-hunt-migration` (24 commits, the full private-hunt migration
plus the 2026-09-12 digest/funnel fix) merged into `main` with
`--no-ff` and pushed: `main` is now `082b9b5`. Verified before merging:
163 personal_hunt tests, 200 Rise tests, 4 rise-web node tests, Ruff
clean, and a clean local production build.

No GitHub-to-Vercel auto-deploy hook exists (confirmed: the newest
deployment via `vercel ls` was 50 days old immediately after the push).
Deployed manually: `vercel --prod` from `rise-web/`, aliased to
`https://rise-web-kappa.vercel.app`, deployment `dpl_GikevKYJNWbq7rTKjFmgDzkJEYa1`.
`/my-hunt` and its JS chunk both return HTTP 200. The page itself needs
a signed-in approved account (`dakshinjain187@gmail.com` or
`dakshjainn02@gmail.com`) to render past the Firebase auth gate, which
cannot be verified from an unauthenticated fetch — Daksh should confirm
in his own browser.

Vercel CLI needs `node --use-system-ca` on this network (same TLS gotcha
as the Modal CLI); the global install lives at
`C:\Users\daksh\AppData\Roaming\npm\node_modules\vercel\dist\index.js`.
`npm run build` locally fails on a broken `node_modules\.bin\vite.cmd`
shim (resolves to a nonexistent `E:\Projects\vite\bin\vite.js`); run
`node node_modules/vite/bin/vite.js build` directly instead. Does not
affect Vercel's own container build, which succeeds normally.
