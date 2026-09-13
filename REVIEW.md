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

## 2026-09-13 — Volume optimization (2->4/day) and funded-company chain unlocked, two more real bugs found live

Plan: `C:\Users\daksh\.claude\plans\wait-i-have-provided-shiny-kazoo.md` (approved by Daksh after
brainstorming/exploration/plan-mode process; not "add anything to hit 5" but "optimize the
workflow" using real funnel data).

**Real diagnosis before any change:** run_6e74f84cd7c98afb showed `linkedin_posts_apify` at
105 raw / 9 of 10 eligible (8.6% yield) against 0.2% for every other source combined. The Kimi
gate was already correct (6 of 8 withheld that day were genuine junk). The bottleneck was source
starvation, not the admission bar — confirmed by checking the two levers that looked attractive
and weren't: only 8 records hit `role_not_cross_functional` solely (cap was 25, not binding), and
only 1 hit `below_publish_threshold` solely.

**Shipped:**
- 7 Apify tokens wired via existing `APIFY_TOKEN_1..7` rotation (zero code). Shared cap 25 -> 33.
- LinkedIn actor + extraction cap tripled 150 -> 300 together (extraction must move with the
  actor cap or paid posts get silently discarded, `skipped_over_cap`).
- New `llm_shortlist_size` (30) split out of `daily_target` (10), which was doing double duty as
  both the pre-LLM shortlist size and the digest's report-text target — eligible records past #10
  never reached Kimi before this.
- `score_shortlist`'s Bedrock call given an explicit `max_tokens=5000` (was the 1800 default,
  which sits right on the truncation edge for a 30-record batch and fails the WHOLE section
  closed on overflow, not just the tail).
- `max_artifacts` 2 -> 6 so the deep-research/prototype chain can cover a 5-admitted day.
- New `resolve_company_url_via_search()` in `firecrawl_research.py`: a third domain-resolution
  pool for funded companies, alongside `company_resolve.py`'s two existing exact-match pools —
  live search, filtered against aggregators/news, then MANDATORY on-page verification (fetches
  the candidate and requires the company's own name to appear on it) before accepting a domain.
  Never guesses. Wired into `pipeline.py` right after the existing `resolve_company_urls` call.
- `company_site.py`'s `CANDIDATE_PATHS` reordered careers/jobs/blog/changelog/engineering before
  about/company/homepage — marketing copy can never support an internal-problem hypothesis per
  the existing Kimi instruction, so operational pages are tried first.
- New `validate_prototype_prompt` in `build_prompt.py` (structural + clone-check validation,
  `build_prompt.py` previously had none, unlike outreach's `validate_outreach`).
- New "Worth a look" digest section (fit 60-69, text + HTML), never counted toward the daily five.
- Outreach's problem-led email now says what the prototype does (`what_to_build` line), not just
  that one exists.

**Real cloud verification, three collect runs:**
- `run_6e74f84cd7c98afb` -> `run_c5e40cce7b37aeed`: admitted 2 -> 4 after the volume fixes.
- Immediately surfaced a real regression: reusing `primary_responsibility()` (built for job-listing
  sentences like "You will own X") on raw company-webpage HTML misclassified a cookie-consent
  banner and Emergent's own product tagline ("Build production-ready apps through conversation")
  as "operational" evidence — worse than the plain SIGNAL_TERMS match it replaced, because ordinary
  marketing copy uses the same ownership verbs. Fixed: basis is now decided by WHICH PAGE the
  evidence came from (careers/jobs/blog/changelog/engineering vs about/company/homepage), not by
  sentence content.
- `validate_prototype_prompt` was checked against `build_prompt.py`'s embedded `PROMPT_TEMPLATE`
  fallback headings ("## Problem", "## What to build"), not the real on-disk
  `templates/prototype_prompt.txt` that `_load_prompt_template()` actually uses ("## Observed
  signals", "## Build the prototype") — would have blocked every real prompt this pipeline
  generates. Fixed, with a regression test built from the real template.
- **Most serious finding**, read from real output, not caught by any test:
  `build_prototype_prompt` never checked `problem_research["supported"]`, only that
  `evidence_urls` was non-empty. A real cloud run showed it generating "Build an internal vendor
  cookie audit dashboard for Lyzr AI's marketing/ops team" from evidence that was literally
  "Vendors Teamtailor Analytics These cookies collect information..." — a cookie-consent banner,
  correctly flagged `supported=false` upstream but never checked downstream. Fixed with a
  fail-closed gate (`llm_status: skipped_unsupported_hypothesis`) matching
  `research_funding_event`'s existing `allow_llm` pattern. Verified against the exact real
  cookie-banner text in a monkeypatched regression test that asserts the LLM is never called.
- Final verification run `run_86a248255b91d32f`: 4 admitted (Kplor 92, Sarvam AI 78, Ressl AI 75,
  Nilo 72), one "worth a look" entry (Sarvam 68), all three watchlist companies correctly
  `skipped_unsupported_hypothesis` — zero hallucinated prototypes.

**Known external blocker, not a code bug, flagged for Daksh:** Firecrawl's `/v1/search` returns
`402 Payment Required` on the current account/plan. `resolve_company_url_via_search` is built,
tested, and fails closed correctly (captured as `company_url_resolution_error` on the funding
event, no crash) — but the funded-company domain-resolution chain cannot exercise live until the
Firecrawl plan is sorted. Both real funding events today (Graph AI, Paris Panini Parent Popo
Global) stayed `unresolved` for this reason, not a matching failure.

Second Opus-model subagent pass (dispatched mid-session per Daksh's request to use Opus for code
fixes) independently audited the `build_prototype_prompt` gate change: confirmed placement and
logic, fixed two existing tests that asserted the old (buggy) behavior, audited every caller of
`prompt_generation["llm_status"]` for a fixed-value assumption (none found), and added the
cookie-banner regression test.

**Verified:** 244 personal_hunt tests (up from 233), 200 Rise tests (separate commands), Ruff
clean. Committed `d2e32ae`, pushed to `origin/main`. Redeployed to `daksh-internship-hunt` three
times across this session (once per real bug found and fixed). One real digest sent, message
`1a096e9228b368fc`, checked against `state.json`'s `digest_deliveries` ledger first (two other
sends already existed for 2026-09-12; Daksh explicitly approved this third one in this session's
plan approval).

## 2026-09-13 (continued) — Firecrawl scoped to funded companies, fresh key wired, resolution verified live

Daksh asked why Emergent/Lyzr/AEOS's problem briefs always come back "insufficient evidence" and
whether recently-funded companies are actually being scraped. Clarified: those three are the
static `watchlist.yml` entries, always shown regardless of evidence; real funding scraping
(Inc42/YourStory RSS -> `funding.py`) is a separate, working feature, but its output never reached
a problem brief because domain resolution needed Firecrawl, and Firecrawl was returning `402
Payment Required` on the existing account.

Checked Firecrawl's real pricing before doing anything else: the free plan does include `/search`
(1,000 credits/month, 2 credits per 10 results, `scrapeOptions` adds ~1 credit/page). Found that
`research_record` (used for every admitted internship + weekly target, ~7 records/run) was ALSO
calling `maybe_add_firecrawl_evidence` on top of its existing free `company_site.py`/HN evidence —
never the intent, and alone burning ~70 of 1,000 monthly credits per run. Removed that call;
internship research is back to free-only evidence. Firecrawl usage is now scoped to only
`resolve_company_url_via_search` (funded companies, capped at 5/run) — worst case ~20 credits/run,
~1,200/month, real usage far lower since funded companies are rare (1-2/day observed).

Daksh supplied a fresh free-tier Firecrawl key. Wired safely: extracted just the
`FIRECRAWL_API_KEY` line from the local `.env` into a scratch-only temp file (never pasted in
chat, never committed), created a new dedicated Modal secret `firecrawl-key`, placed after
`internship-hunt-secrets` in `pipeline_secrets` so it overrides the old dead key (Modal secrets
apply in list order). Temp file deleted immediately after.

**Verified live** (`run_b57aa67fbd11006f`): Graph AI resolved to `graphsafety.ai`,
`company_url_basis: firecrawl_search_verified_onpage_name`, no 402. Read the match by hand — the
verifying text was the site's own footer, `"© 2026 Graph AI Services, Inc."`, a genuine on-page
name match, not a false positive. Second funded company that day (`Paris Panini Parent Popo
Global`) correctly stayed `unresolved` with no error rather than guessing. Admitted internships:
5 that day.

**Honest caveat, not yet resolved:** Graph AI's `problem_status` still came back
`insufficient_evidence` even with a resolved domain — the resolution step works, but a brand-new
Series A company's site mostly has marketing copy so far, and the pipeline correctly refused to
invent an internal-problem hypothesis from it rather than fabricate one. The full resolve -> real
hypothesis -> prototype -> contact chain has not yet been observed succeeding end to end on a real
company; that is the next thing to watch for on a funded company with richer public evidence
(engineering blog, more open roles, etc.).

Verified: 244 personal_hunt tests, 200 Rise tests (separate commands), Ruff clean throughout.
Committed `83ec1e9` (Firecrawl scoping) and `d2cd7f6` (key wiring), pushed to `origin/main`,
redeployed twice. One real digest sent for the new run, message `1a09783b537a4647` — the second
send today (2026-09-13), both explicitly requested by Daksh in this session.

## 2026-09-13 (continued) — Funded-company chain works end to end for the first time

Daksh's own question ("so is the whole pipeline working now") exposed the real remaining gap:
resolution worked, but `research_deep_problem` had exactly two evidence sources — the company's
own site and Hacker News — which was consistently too thin for a young, recently-funded company
to ever produce a supported hypothesis. Correct behavior on thin evidence (refuse rather than
invent), but useless in practice: every funded company came back `insufficient_evidence`, every
day, with no path to ever change that.

**Fix:** wired a third real evidence source into `research_deep_problem` — Firecrawl search for
third-party mentions of the company (news, community posts), via the existing
`search_public_evidence` function. Two bugs fixed in that function before it was usable: it
emitted `type`, not the `basis` field the Kimi instruction actually checks (a mismatch that would
have made this evidence silently invisible to the model even once wired in), and it was cut from
2 queries + `scrapeOptions` to 1 query with no scrape to fit the free plan's 1,000 monthly credits
now that it runs as a real, scoped pipeline stage rather than sitting unused.

**Scoped to skip the 3 watchlist companies** (Emergent/Lyzr/AEOS) — same fixed names every run, so
a fresh daily search for them is pure waste. Real funded companies (new each day, capped at
`max_deep_research_per_run`) are the only case worth paying credits for.

**Verified against a real cloud run** (`run_44cb9526ef7b738e`): Graph AI's evidence count went
2 (site only) -> 8 (site + HN + Firecrawl), `supported: false -> true`, and produced a real,
validated, non-clone prototype — an internal "Handoff Protocol" dashboard for cross-team
coordination friction, grounded in verbatim quotes from `graphsafety.ai/careers` and `/company`,
plus an honest `contact_research_required` status sourced to the real YourStory funding article.
**This is the first time the full chain — resolve -> evidence -> hypothesis -> validated prompt ->
contact — has been observed succeeding end to end on a real company.** Watchlist companies'
evidence counts were unchanged from the prior run, confirming the skip guard held (no wasted
credits on them).

Verified: 250 personal_hunt tests (up from 244), 200 Rise tests (separate commands), Ruff clean.
Committed `7726c2d`, pushed to `origin/main`, redeployed, verified live before pushing.

## 2026-09-13 (continued) — Hunter wired to every call site, discarded emails restored, email body replaced with a Claude Code prompt, watchlist daily burn stopped

Daksh raised three problems: zero contacts ever reached him despite Hunter.io being connected;
the drafted emails read as mail-merge slop, worse than plain AI slop; and Emergent/Lyzr/AEOS burn
two Kimi calls each, twice daily, for a permanent `insufficient_evidence`.

**Diagnosis, not assumption, first.** Before touching code: listed the mounted Modal secret
`internship-hunt-secrets` via a throwaway `modal run` function that printed only whether
`HUNTER_API_KEY` was present (never its value) — it was, 40 characters, matching Hunter's key
format. That ruled out the obvious "key never reached the cloud" theory. Calling
`hunter.account_quota()` locally against the same key then hit a real local bug: `.env` line 108
had `HUNTER_API_KEY=...422b8967PUBLIC_RESEARCH_PROVIDER=firecrawl` on one line with no newline
between them, so the local key was 74 characters of two concatenated values and every local
Hunter call 401'd. Fixed the line break; `account_quota` then returned `(50, 100)` -- untouched
free-tier quota, confirming Hunter really has never run once, matching the absent `hunter` key in
`state.json`. `domain_search` against `stripe.com` (a domain known to have staff) confirmed the
real shape of a Hunter pick: `sources[]` is frequently a Google search-query URL
(`google.com/search?q=site:linkedin.com...`), not a direct citation link -- the code already
caps confidence at `medium` for this (never `high` without a separate deliverable-verification
call), so no code change was needed there, only precise wording in the policy amendment below.

**Five real breaks found by reading the code, not guessing:**
1. `find_company_contact` only ran inside `enrich_selected`'s `research_queue`
   (`pipeline.py`) -- funding events (`:727`, old numbering) and
   discovered/watchlist companies (`:774`) called bare `choose_contact` with no Hunter fallback at
   all. Those are exactly the records that get deep research and a validated prototype prompt.
   Confirmed against the 2026-09-13 Graph AI run: real domain resolved, real careers page fetched
   and quoted, still ended `contact_research_required`.
2. `problem_research.py:228` unpacked `_fetch_site_and_roles`'s scraped emails into `_emails` and
   discarded them -- none of `research_deep_problem`'s five return dicts carried
   `published_emails`, though all five carried `published_linkedin_urls`.
   `contacts._site_email` only ever read `research["published_emails"]`, never
   `deep_problem_research["published_emails"]`.
3. `hunter.py`'s `except Exception: return None` made every early return (missing key, blocked
   domain, monthly cap, a real HTTP error, and a genuine no-match) look identical from outside.
4. `digest.py`'s internship section printed `contact.name or contact.status` -- a site-scraped or
   Hunter-found address with no name (`site_published_role_mailbox`, or an unverified generic
   Hunter pick) rendered as the bare word "available" with the email nowhere on the page.
5. The `email_body` on every draft was a hardcoded Python f-string in `outreach.py`
   (`draft_problem_led_email`, `draft_outreach`) -- Kimi K2.5 has never written outreach copy,
   only ranking/research/prototype-prompt generation. Every email was the same skeleton with the
   company name swapped in.

**Fixes, in the order that unblocks Daksh soonest:**

- **`pipeline.py --watchlist-prompts`** (new, `execution/watchlist_prompts.py`): deterministic,
  no fetch, no LLM. Writes one self-contained deep-dive prompt per `watchlist.yml` company to
  `out/<date>/watchlist-prompts/<slug>.md` -- verified facts from the config, a research brief
  with the same truth rules as `CLAUDE.md`, and the email copy rules plus a `/humanizer`
  instruction. Daksh pastes one into a fresh Claude Code conversation per company.
- **`contacts.attach_contact(record, hunter_ctx)`** is now the single path all three call sites
  route through (`pipeline.py`'s `enrich_selected`, the funding-event loop, and the
  discovered/watchlist loop) -- replacing three separate, inconsistent call sites with one.
- **`problem_research.py`**: kept the previously-discarded scraped emails and added
  `published_emails` to all five `research_deep_problem` return dicts. `contacts._site_email` now
  reads both `research` and `deep_problem_research`, mirroring the two-source merge
  `_extract_provenanced_linkedin` already did for LinkedIn URLs.
- **`hunter.find_company_contact_with_status`** (new): every early return now carries a reason
  (`no_api_key`, `no_domain`, `cached_miss`, `cap_reached`, `quota_exhausted`, `no_match`,
  `http_error:<code>`, `cache_hit`, `ok`). `find_company_contact` (the old signature) still exists
  as a thin wrapper for backward compatibility. `pipeline._hunter_source_health` aggregates every
  status collected across a run into one `hunter` source-health row, rendered in the digest's
  existing Source health section -- a `no_api_key` line there would have caught this whole class
  of problem on day one.
- **`digest.py`**'s internship section now prints the email, its source URL, and its
  `contact_priority` whenever present, not just the name-or-status line.
- **`outreach.build_email_prompt(record)`** (new) replaces `email_body` with `claude_prompt` in
  both `draft_problem_led_email` and `draft_outreach` -- a self-contained, paste-ready prompt
  (new `templates/email_prompt.txt`) carrying the company, contact, the real observed signal with
  its source, the inference kept explicitly separate from it, the uncertainty, the solution idea,
  the resume basename, the copy rules, and a `/humanizer` instruction. The forbidden-word/phrase
  lists are rendered from `outreach.py`'s own `FORBIDDEN_WORDS`/`FORBIDDEN_PHRASES` constants, not
  retyped, so the rules Claude Code is told to follow cannot drift from what `validate_outreach`
  enforces. Refuses to emit an empty prompt: `send_status` becomes `blocked_no_evidence` when
  there is no real observed signal to ground one in, distinct from `blocked_insufficient_evidence`
  because LinkedIn note/message are still drafted in that case. `validate_outreach`'s email
  word-count and subject-format checks were removed (they validated a field that no longer
  exists); every LinkedIn and tone/forbidden-content check is unchanged. `sheets.py`'s Outreach
  tab `email_body` column is now `claude_prompt`; fixed a real adjacent bug in the same edit --
  the `subject` column read `draft.get("subject")`, a key neither draft function has ever emitted
  (`email_subject` is the real key), so that column was silently blank on every real run.
- **One real bug found while smoke-testing the new prompt by hand**: `deterministic_research`'s
  own observation reads `The listing states: "..."` -- wrapping that again in quotes for the
  prompt nested them (`""..."`.`") and read as visibly broken. Fixed with `_quote_with_source`,
  which skips the outer wrap when the text already quotes itself.
- **`watchlist.yml`**: `deep_research: false` (new, default). `pipeline._watchlist_to_companies`
  now always builds the display list (free, no fetch or LLM) for the digest's watchlist movement
  section; whether that list also enters the daily deep-research queue is gated separately at the
  `select_discovered_for_research` call site. `watchlist_board_sources` (the actual job-board
  fetch) is untouched and still runs every time -- it is real, cheap signal, unlike the daily
  research pass. The Watchlist movement section now reads each company's own board-fetch
  `record_count` from `source_health` when it wasn't deep-researched this run, instead of showing
  a dishonest "no activity" for a signal that was never checked. New `fetch_sources.watchlist_source_id`
  is the one place that slug is computed, shared between the fetcher and the digest so they can
  never drift out of matching each other.
- **Policy amendment**, `context/source-and-access-policy.md` (archived workspace, 2026-09-13):
  replaced the blanket "No automated personal-contact discovery" line with the rule the code now
  enforces -- a named-person address is acceptable only with at least one public source URL,
  stored with its extraction date and confidence; a pattern-guessed address is never stored or
  shown regardless of provider. Documents the Google-search-query nuance in Hunter's `sources[]`.

**Verified:** 264 personal_hunt tests (up from 250), Ruff clean. `Step 0` diagnostics run live
against the real Hunter account (`account_quota` returned `(50, 100)`; `domain_search` against
`stripe.com` returned real named picks with the expected `sources[]` shape). Fixture run's
rendered digest inspected by eye for the Watchlist movement section text. `build_email_prompt`'s
output inspected by eye twice -- once to confirm the doubled-quote bug, once after the fix.
`pipeline.py --watchlist-prompts` run for real; all three generated files read end to end.

**Skipped or unverified:**
- **No live cloud run yet** with these changes deployed -- not committed, pushed, or redeployed
  this session. The next scheduled run is the first real test of Hunter actually firing on a
  funded/watchlist company with a resolved domain.
- **HUNTER_API_KEY was already correctly present in the mounted secret** -- the original
  suspicion (never reached Modal) was wrong; Step 0 caught this before any secret was rewritten,
  so no Modal secret change was made this session.
- Sheets publish, Gmail self-digest, and the funded-company end-to-end chain were not re-verified
  live in this session; those paths are exercised by the existing test suite and the 2026-09-13
  (continued, above) entry's live run, not by anything new here.

## 2026-09-13 (continued) — Pipeline reviewed from Daksh's side; ten ranked fixes

Reviewed the whole flow as Daksh would live it: the email, `/my-hunt`, the prompts, the resume
choice. Diagnosis came from the stored run artifacts, not assumption. The headline: discovery
finds real, on-target roles (Kplor, SuprSend, Sarvam AI, Ressl AI on `run_21ae706418041f9a`),
but most paid leads died before approval, and the ones that got through reached Daksh with no
contact, no prompt, and sometimes the wrong resume.

Ranked by how much each raises the number of leads reaching Daksh and his odds of converting one.

**Most important**
1. `c95c1c5` LinkedIn extraction required employer, title and location in one 300-character
   quote. Real posts name the employer in line one and the role ~880 characters later
   (Auraaison). Five consecutive live runs resolved 16/28/31/27/33 of ~100 paid posts. Each
   field is now grounded against the whole post; an empty company no longer counts as resolved.
2. `19b4e2b` 26% of qualified hiring posts print an application address in the body, and
   nothing read it. `contacts.listing_emails()` now does, cited to the listing URL. Records with
   a name or LinkedIn profile but no email also get the lookup now. 2 → 4 of 13 digested
   records have an email.
3. `6d3ce45` Every "problem" was a template ("The breadth of {role} may create a need..."), the
   observation fallback restated that a job was posted, and Kimi's research merge could overwrite
   a real quote with a paraphrase. The verb matcher now finds a quotable work sentence in 8/13
   digested records (was 3/13); an observation from Kimi survives only if its quote is verbatim.
   Records with no observation get a research-first Claude Code prompt instead of nothing. The
   LinkedIn notes stopped claiming a brief or a prototype that did not exist. Prompts and
   contacts now render in the markdown digest, the HTML email and `/my-hunt`. `/my-hunt` had been
   reading `outreach.subject`/`email_body`, which no draft emits, so it said "No validated email
   draft" on every match. Replay of `run_21ae7064`: 4 blocked → 0 blocked, 1 grounded prompt,
   3 research-first.
4. `3812101` The resume was chosen from the description ("high-growth" → GTM resume on 471 of
   1,458 records). It is now chosen from the title only. Sarvam AI "Strategy and Operations
   Intern" moves from GTM to Founder's Office.

**Less important**
5. `ced22d0` The HTML email now explains a zero-match day instead of rendering an empty table.
   It also shows failed sources, staleness and spotted leads, with actionable sections first.
6. `f9c5a2b` The watchlist line says "N open roles, M fit your filters", "board not fetched
   this run", or "no public job board -- watch the founders' posts". It no longer prints "no
   board configured" for boards that are fetched live.
7. `cd610e5` `/api/personal/latest` no longer 503s when the Kimi gate fails. The page shows a
   banner and keeps funding, verification and source health visible.

**Least important**
8. `90ccb70` `manually_applied`/`replied`/`interviewed` were 0 on every run because nothing
   read the Sheet's human-owned Outreach columns. Publish runs now read them (read-only, same
   credential) and the digest prints lifetime outcomes and which sources got replies.
9. `e264955` Day 3/8/14 follow-ups, drafted since the start and never shown, now appear as
   "Follow-ups due today", from the Sheet's `sent_at`.
10. `16f6f5c` Send-queue roles whose page says "position filled" / "no longer accepting" (200
    status, so the HEAD link check misses them) move to "Probably closed". Live runs only, at
    most quota+3 GETs, robots-respecting, never LinkedIn. `execution/hunt_core` was left
    unedited because it is shared with public Rise.

**Verified:** personal_hunt suite passes throughout (tests added for every change; seven
existing expectations updated where the contract changed on purpose), Ruff clean, rise-web
`npm test` 4/4 and `vite build` succeed, fixture pipeline run after each commit. The live GET
for #10 against the real Ressl AI YC listing returned no closed signal.

**Skipped or unverified:**
- **Nothing pushed or redeployed.** Ten commits on local `main`. No live cloud run exercises
  any of this yet. After deploy, read the first run's `linkedin_posts_apify_extraction` row
  to confirm resolved/attempted rises above ~0.3.
- **Live Sheet read for #8/#9 not run.** `INTERNSHIP_SHEET_ID` is only in the Modal secret.
- **#10 positive path is unit-tested only.** No known-closed listing was available to test.
- **Per-record deep research for internships was not enabled.** It would push Firecrawl past
  its 1,000/month free plan, which funded companies already use. That needs Daksh's decision on
  a paid tier. The research-first prompt covers the gap with his own Claude Code session.
- **rise-web deploy (Vercel) not triggered.** The `/my-hunt` fixes ship only when it deploys.
- Windows note: `npx` breaks on the `&` in this repo's path. Run
  `node node_modules/vite/bin/vite.js build` instead.

## 2026-09-13 (continued) — Pushed and deployed; job pages read; Gmail fills the Sheet; paid research tested and rejected

Daksh approved the push, allowed opening LinkedIn in Chrome for verification, approved paid
Firecrawl only if output proved better within the free tier, kept resume metrics as they are, and
asked for the Sheet's outcome columns to fill automatically.

**Deployed:** 11 commits pushed; Modal app redeployed; rise-web deployed to Vercel production and
the live `MyHunt` chunk confirmed to contain the new prompt/contact/banner code. Then two more
commits (`def7ae5`, `c4e90cd`), pushed and redeployed; the cloud `fixture_pipeline` completed on
the new code.

**Leads checked by hand in Chrome (logged out, no sign-in wall bypassed), 2026-09-13:**
all six still open. Kplor FO Intern (₹50k/month, PPO ₹12 LPA, 73 comments, founders tagged
Mukil Vannan, Sanjeeth Baliga). SuprSend "Founder's Office - Internship" LinkedIn job (200+
applicants; the JD is partnerships, community and cold-outreach experiments; 3 months in office;
poster Tushar Bhati invites direct reach-out). Sarvam AI Strategy & Operations Intern on Ashby
(revenue systems, CRM, funnel analysis). Ressl AI GTM Intern on YC (₹40k–1L/month; CEO Arushi
Gandhi says "do not use AI to write it" and asks about evals). Ethereal Labs FO Intern/Associate
on binary.so (form open, asks for 1–3 years but allows <1). Auraaison: real but pre-launch site
("coming soon 2026"), 5 LinkedIn followers.

**Internship deep research — built, measured, not shipped.** Live on those four matches:
20 credits (982 → 962 on the cloud key; plan resets 2026-09-22), generic hypotheses, the hiring
post recycled as evidence, and `dev@company.com` from docs.suprsend.com as a contact. Reverted.

**Shipped instead (`def7ae5`):** full job page behind each approved link (Ashby/Greenhouse/Lever
public APIs, otherwise one robots-respecting GET, never LinkedIn), live runs only, bounded. Every
prompt now carries the listing verbatim. When a listing asks for no AI-written messages, the
prompt refuses to draft and both digests flag the card. Contacts: role mailboxes (info@, hr@)
are no longer ranked as people; site-scraped addresses must be on the company's own domain;
documentation placeholders are never contacts.

**Gmail → Sheet (`c4e90cd`):** fills sent_at / send_status / reply_outcome / interview_outcome
from Gmail evidence, never overwriting typed values, recording the message id in
`outcome_basis`. **Flagged, not active:** needs a gmail.readonly token for the account Daksh
sends from (`mint_gmail_token.py --readonly`), pasted into the new, currently empty, Modal secret
`internship-hunt-gmail-read`. `INTERNSHIP_SHEET_ID` and the Sheets token are confirmed present
in the cloud (presence only, values not read).

**Verified:** 304 personal_hunt tests, Ruff clean, fixture run local and in the cloud, live page
fetches for Sarvam/Ressl/Ethereal, replay of four real matches with 0 validation errors.

**Not verified:** Gmail sync against a real mailbox (no read token yet); a scheduled live run on
the new code (next one is 00:30 IST, 2026-09-14). Ressl AI's quoted sentence is still the company
tagline; the full page in the prompt carries the actual role text. LinkedIn job pages (SuprSend)
are still not read by the pipeline. Daksh's Chrome permission covers interactive checks, not the
scheduled scraper.
