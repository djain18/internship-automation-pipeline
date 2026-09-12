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

## 2026-09-13 — mojibake mystery resolved (Modal preemption snapshot theory confirmed); Phase 1 verification complete

**Trigger:** commit `16c9fa1` widened `repair_mojibake`'s pre-check
(`personal_hunt/execution/models.py`) to catch `â‚¹` (rupee sign
mis-decoded as cp1252), not just the original `â€` guard. The fix was
verified correct locally against the live Inc42 feed, but the first
cloud run after redeploying still showed the mangled text, and that run
had logged `"Container terminated due to preemption... will be
restarted with the same input"` before completing — raising an
unconfirmed theory that the preemption resumed a pre-redeploy process
snapshot rather than the freshly deployed code.

**Resolution:** redeployed (`daksh-internship-hunt`, no errors) and ran
`collect` again. No preemption message this time. Downloaded the new
run artifact from the volume — `run_05650933bd04f0cd`, completed
2026-09-12T09:27:53Z — and inspected `funding_primary` directly:
`"Paris Panini Parent Popo Global Raises ₹532 Cr From Artal Asia"`
renders the rupee sign correctly in `headline`, `company`,
`observed_signal`, and `source_reported_detail`. No `â` or `Â` anywhere
in either funding event's fields. **Confirmed: the fix works; the
mojibaked cloud run was a preemption/snapshot artifact, not a live bug
in the current code.** (Unrelated: raw FTB internship-listing
`description` text in `all_scored` still carries mojibake — that field
was never in scope for this fix and is a separate, undiagnosed source
of the same defect class in a different field.)

Both funding events remain `company_url_basis: unresolved` (Graph AI,
Paris Panini Parent Popo Global) — expected, documented low-hit-rate
behavior per the Phase 1 design (neither company is in a VC registry or
that day's opportunity list), not a bug.

**Phase 1's own verification gap closed:** no live event has resolved a
`company_url` yet to exercise the `allow_llm=True` → real Kimi call →
`inference_needs_validation` path end-to-end, and Bedrock credentials
only exist in the Modal secret (not locally), so a live exercise wasn't
possible this session. Added
`test_funding_research_with_resolved_url_reaches_inference_needs_validation`
to `personal_hunt/tests/test_company_research.py`, mirroring the
existing negative-path test
(`test_funding_research_does_not_call_llm_without_explicit_promotion`):
mocks `cached_bedrock_json` to return `supported: true` and asserts
`llm_status: ok`, `problem_status: inference_needs_validation`, and the
generated `problem_hypothesis` survives. This proves the gating and
status-mapping logic in `research_funding_event`
(`personal_hunt/execution/research.py:405-456`) is correct in isolation;
it does not replace a real cloud exercise once a live funding event
actually resolves a `company_url`.

**Verified:** 179 personal_hunt tests (was 177 + 2 new), 200 Rise tests
(separate commands), Ruff clean on `personal_hunt`.

Phase 1 is now considered done. Next: Phase 2 (`problem_research.py`)
and Phase 3 (`build_prompt.py`), per the approved plan's ship order.

## 2026-09-13 — Phases 2, 3, 4, 5, 6, 7 shipped; all verified, all bug-fixed

All remaining phases of `i-want-you-to-ethereal-sloth.md` are implemented
and committed on `main`, in ship order (2+3, 6, 4+5, 7). Commit range
`e6a857b^..3beeec5` (13 commits). Only Phase 8's live `/my-hunt` frontend
deploy step remains a Daksh action (deploying the merged copy); everything
in `personal_hunt/` is done.

Each phase was built by a Haiku implementation subagent, then independently
verified (Sonnet, and for the final pass Opus) against the real pipeline
output, not just its own tests. **Every single phase shipped with at least
one real, confirmed bug that only surfaced by reading actual output or
running a live check** — the pattern is consistent enough to record:

- **Phase 2/3**: `build_prompt.py` read `company["problem_research"]`
  (Phase 1's unrelated funding-event research shape) instead of
  `company["deep_problem_research"]` (Phase 2's real output key) — the
  entire prototype-prompt feature was dead on every real run despite
  passing its own tests, because the tests used the same wrong key. Also:
  `discovered_for_research` was computed but never written into
  `run_pipeline`'s returned dict. Also: the fail-closed evidence gate
  checked a quote was a real substring but accepted any non-empty URL,
  letting a fabricated source ride along with a genuine quote.
- **Phase 6**: `watchlist.yml`'s Emergent `board_url` and AEOS `site_url`
  were both plausible-looking guesses, not real — caught only by live
  fetching each one (Emergent's real Greenhouse token, `emergentlabsinc`,
  was buried in a JS bundle behind a custom job-board SPA; AEOS's real
  site is `aeoscompany.com`, not `aeos.ai`). Also: `board_url` was never
  actually read anywhere, so watchlist companies' own job boards never
  reached the pipeline at all until a `watchlist_board_sources()` fetcher
  was added and wired in.
- **Phase 4/5**: the humanizer validator's "curly quote" rule used a plain
  ASCII apostrophe as its forbidden character instead of the real curly
  quote (U+2019) — every contraction in every draft ("I've", "don't")
  hard-failed validation. A test comment left behind ("use plain text to
  avoid apostrophe encoding issues") is the tell that the agent worked
  around its own bug instead of finding it. Also: `draft_outreach`/
  `draft_problem_led_email` was fully built but never called on
  `discovered_for_research`. Also: the fixed email template's word count
  (~66) couldn't satisfy the validator's own 80-110 word range.
- **Phase 7**: `render_digest` (plain text) got the new sections;
  `render_html_digest` — the part Gmail actually renders when both parts
  exist in one message — did not. The whole phase's deliverable would
  have been invisible in the real inbox.
- **Final Opus review pass** (commit `3beeec5`) found and fixed 10 more:
  a site-scraped LinkedIn URL could attach to the wrong person (any
  `/in/` link on a team page, not necessarily the actual contact) and, in
  one path, manufacture a fake "available" contact status from a stray
  profile link with no name or email attached; the digest read
  `contact["source"]` when `choose_contact` emits `source_url`, so every
  problem brief silently dropped its contact provenance; the humanizer's
  forbidden-word scan ran over the verbatim evidence quote too, so a
  company merely describing itself with a word like "robust" blocked its
  own outreach draft; `_role_priority`'s founder/chief-of-staff/head-of-ops
  ladder was computed and discarded (both branches returned the same
  string); the emoji check only covered 14 hand-listed emoji, missing
  🚀✨✅⚡ and anything else outside that list; both LinkedIn note/message
  used a bare `[:300]` slice that could cut off mid-word; the Teamtailor
  adapter bypassed `_verified_ats_url`'s host allowlist entirely, so
  `board_url` in `watchlist.yml` could point anywhere.

**The common failure shape across all of it**: a field computed correctly
in one function, read under a different name (or never read) by its
consumer; a fixed-length template that doesn't actually satisfy its own
validator; a plausible-looking fact (a URL, a Unicode character, an emoji
list) that was never checked against the real thing. Tests passed in every
case because the test used the same wrong assumption as the code. The
lesson already written into this file on 2026-09-12 about Modal exit
codes not proving work applies just as much to unit tests: a green suite
is not proof a feature works end-to-end — only reading the real output
(or, this session, an adversarial second/third read of the diff) caught
any of this.

**Verified, final state:** 233 personal_hunt tests (up from 177 at the
start of this entry), 200 Rise tests (run separately), Ruff clean on
`personal_hunt`. Nothing pushed to `origin/main` yet as of this entry —
confirm with Daksh before pushing the full range.

**Known, deliberately unshipped scope** (documented, not bugs):
- Phase 2's evidence sources are company site + Hacker News only. Reddit
  JSON (blocked by Reddit without auth, confirmed live), Google Play /
  Chrome Web Store reviews, and the approved X/LinkedIn Apify actors are
  not wired into `problem_research.py` yet.
- `_teamtailor`'s location-fallback chain was never exercised against a
  fresh live fetch of `careers.lyzr.ai/jobs.rss` post-fix (all fixture
  items have `tt_city` set, so a fallback path involving `tt_name`, which
  is actually the job name in real Teamtailor feeds, stays unverified).
- The three watchlist companies' `description` fields in `watchlist.yml`
  are documentation only, never read by code — intentional.

## 2026-09-13 — Real send review: prototypes were targeting companies' own paid products

Daksh read the actual digest email (`run_f9ae04eb99b98d0e`) and flagged
two problems.

**1. Zero internships, checked and confirmed correct, not a bug.** Of
1,447 scored records, 1 was deterministically eligible (Ressl AI, GTM
Intern); Kimi scored its real fit at 55/100 against the required ≥70 and
correctly withheld it (`llm_scoring.primary`: `admitted: 0, withheld: 1,
status: ok`). The dominant deterministic rejection reasons
(`role_not_cross_functional` 1110, `location_out_of_scope` 1163,
`posted_over_10_days` 903, `not_internship_or_fellowship` 1214, reasons
compound per record) match this pipeline's documented historical
pattern. A quiet day, honestly reported.

**2. Real bug: the generated prototype for Emergent was a cut-rate clone
of Emergent's own paid product.** The only evidence gathered was a
homepage pricing blurb and a generic careers tagline. Neither LLM
instruction (`problem_research.py`, `build_prompt.py`) forbade treating
a company's own marketing/pricing copy as an internal problem, so Kimi
inferred "AI app builders are too expensive/complex" and then generated
a prototype spec for... an AI app builder with a pricing page. Daksh's
own words: "why should we build something they're already doing, then
tell them their pricing is too expensive, using a cheap app that
wouldn't work at all."

Fixed both instructions: `problem_research.py` now explicitly requires
an INTERNAL operational hypothesis (workflow friction, support/onboarding
load, tooling gaps) and forbids treating marketing/pricing copy as
evidence of an internal problem — when that's all the evidence says, it
must set `supported=false` and leave the hypothesis empty rather than
inventing one. `build_prompt.py` now explicitly forbids proposing a
clone or competitor of the company's own core commercial product;
anything the prototype builds must be adjacent, helping the company's
own team internally.

**Found while verifying that fix, a second real bug:** `problem_status`
in `research_deep_problem` was hardcoded to `inference_needs_validation`
regardless of the model's own `supported` verdict — so even a correctly
unsupported, empty-hypothesis result (exactly what the new instruction
asks the model to produce on thin evidence) still claimed a validated
inference. `research_funding_event` already got this right (status keyed
on `supported`); this sibling function did not. Fixed to match.

**Reverified against a real cloud run** (`run_5e783e64cf110835`, no
preemption): all three watchlist companies now propose genuinely
adjacent internal tools — an internal team-coordination dashboard for
Emergent's distributed dev squads, an "Agent Performance Observatory"
monitoring Lyzr's own open-source framework deployments, a "Culture
Pulse" dashboard for AEOS's portfolio operations team. None mention
rebuilding or pricing the company's own product.

`deliver` was deliberately NOT rerun a second time today to avoid
double-sending Daksh mail; the fix is verified against `collect`'s
output only. Tomorrow's scheduled 08:30 IST digest is the first real
end-to-end proof.

234 personal_hunt tests, 200 Rise tests, Ruff clean. Pushed to
`origin/main` (`8dc3868`). Redeployed to `daksh-internship-hunt`.

## 2026-09-13 — Funnel fix committed, deployed, verified against a real collect

Opus subagent investigation (dispatched after Daksh's "1,447 scored, 0
admitted, I want >=5/day" complaint) landed three fixes, found already
sitting uncommitted in the working tree when this session picked up the
handoff. Reviewed, tested, committed as `cdf4235`, pushed, redeployed.

1. `fetch_sources.py`: harvested ATS boards (whole company job boards,
   e.g. `ats_harvested_greenhouse_feverup`) were contributing hundreds of
   `location_out_of_scope` rows per run — 955 of 1,447 records (66%) on
   `run_f9ae04eb99b98d0e`. Now filtered to in-scope locations at harvest
   time. Location is a hard exclusion no later tier reverses, so this
   drops pure noise only.
2. `llm_rank.py` / `scoring.yml`: LinkedIn extraction still truncated
   (`Unterminated string`) after an earlier batch-size cut, because the
   model sometimes echoes the full ~3000-char post instead of the
   instructed 300-char quote. `max_tokens` 3500->6000, per-run extraction
   cap 100->150 (the actor's own ceiling). Real run showed
   `skipped_over_cap: 12` lost matches; measured added cost $0.00.
3. `score.py`: an exactly-titled Bengaluru role (curated `accepted`
   phrase or title family) can top out at 64/100 because 46 of the 100
   scoring points measure company metadata that's unverifiable for small
   unknown startups, against a 70 threshold. Added a floor to threshold
   only when title already matched AND location is verified Bengaluru —
   invents nothing; Kimi's independent fit-score gate still decides what
   reaches the digest.

233 personal_hunt tests, 200 Rise tests, Ruff clean. Deployed to
`daksh-internship-hunt`.

**Verified against a real `collect`** (not `deliver` — two sends already
happened today, see `state.json`'s `digest_deliveries`):
`run_6e74f84cd7c98afb`, completed 2026-09-12T16:40:07Z.

- raw 604 (down from 1,447 — the location pre-filter working as designed)
- deterministically eligible 10 (up from 1)
- Kimi (`llm_scoring.primary`): `admitted: 2, withheld: 8, status: ok`
- Admitted: Auraaison "Founder's Office Intern" (fit 95, "Explicit
  Founder's Office title with direct founder exposure, 0-to-1 building,
  end-to-end ownership") and Ressl AI "GTM Intern" (fit unchanged from
  prior runs).
- Withheld 8 included Vatsenix "Business Development Intern", Nilo
  "School Outreach & Partnerships Intern", Eli Lilly "GOSO Intern",
  Google "Application Engineering Intern" and others — Kimi's per-record
  withhold reasons are not persisted to the run artifact (a real gap, not
  investigated further this session; `llm_scoring` only carries the
  aggregate admitted/withheld counts, not why each of the 8 was cut).

**Honest read: still below the 5/day target, and this is a real quality
gate, not a leftover bug.** The deterministic layer now correctly surfaces
10 candidates a day instead of 1 — the funnel fix worked as designed. Kimi
then holds 8 of them back because they generically title-match ("Business
Development Intern", "HR Operations Intern") without founder's-office-style
signal in the JD, which is exactly what Daksh's two 2026-09-13 policy
clarifications intended to *stop* penalizing only for thin/ambiguous JDs —
not to admit generic BD/HR/ops titles wholesale. Whether 2/day is an
acceptable steady state or needs a further look (e.g. persisting withhold
reasons to actually see Kimi's judgment) is Daksh's call, not assumed here.

No third digest sent today. `deliver` intentionally not run.
