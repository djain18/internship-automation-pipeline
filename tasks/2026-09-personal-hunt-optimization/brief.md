# Brief: Rise personal hunt optimization

Date: 2026-09-11
Status: approved by Daksh Jain

## Outcome

Make `personal_hunt` the sole maintained personal internship runtime, improve
high-fit supply and evidence-backed outreach, and cut repeated paid/LLM work
without weakening freshness, provenance, or manual-send controls.

## Approved decisions

- Keep the 10-day internship freshness window.
- Preserve the $5 total Apify ceiling and $0.25 per-run cap.
- Require explicit paid-source authorization; ordinary dry runs spend nothing.
- Add free public ATS discovery and a separate Monday founder-target lane.
- Prefer named public contacts and allow verified generic company inboxes only
  as lower-priority fallbacks.
- Measure seven optimized scheduled runs before proposing a Bedrock/Modal cap.
- Keep every application and prospect message manual.

## Amendment 2026-09-11 (Daksh Jain)

- LinkedIn actor runs on every scheduled run, not only below five candidates.
- Per-run cap raised $0.25 -> $0.70; monthly hard stop set to $25 shared across
  all keys (~30 daily full-price runs, then the stop holds).
- Seven-key rotation across Daksh's own accounts (`APIFY_TOKEN_1`..`APIFY_TOKEN_7`):
  first usable key wins, exhausted/unauthorized keys are skipped, all-unusable
  fails closed. This supersedes the earlier never-rotate rule. Slots are logged,
  key values never are.
- Evidence note: the 2026-09-11 $0.03905 probe mapped 19 posts with zero
  eligible, so every-time spend is on unproven precision. Re-measure yield over
  the next scheduled runs before any further cap change.

## Delivery proof 2026-09-11 (Daksh confirmed receipt)

- 08:30 IST cron delivered 3 matches; Gmail message ID in the state ledger.
- Manual `deliver` correctly skips when nothing new (no double-send).
- Either Daksh alias accepted as recipient; sends From the configured address.
- Sheet publish proven against the live tracker (52 Companies, 2 Opportunities,
  2 Outreach rows per run; human-owned columns merge-preserved).

## Implementation slices

1. Stabilize Rise ownership and record the externally initiated HarvestAPI run.
2. Repair LinkedIn-post normalization and add a paid-source CLI gate.
3. Move Kimi/research behind cheap gates and cache by content/prompt/model.
4. Add public Greenhouse, Lever, Ashby, and Workable watchlist adapters.
   Harvest vendor board links embedded in jobs.accel.com into reviewed ATS
   API sources each run (slugs from discovered links only, capped at 8).
5. Add company provenance, weekly targets, outreach strategies, outcomes, and
   source/cost reporting.
6. Verify fixtures, both Python suites, frontend tests/build, and safe dry runs.
7. Add Hunter.io contact finder (free tier) behind monthly caps and cache.
8. Expand supply where it is policy-clean; retire structural zeros with cause.

## Amendment 2026-09-11 (Daksh Jain): supply diagnosis

- Measured yield: YC Bengaluru carries, FTB contributes, Rise sheet is mostly
  stale, LinkedIn posts are low-precision, WWR is out of scope by design.
- Wellfound retired: its public page serves full-time listings only.
- ATS harvester added: vendor board links embedded in jobs.accel.com convert
  to the vendors' public board APIs (slugs from discovered links only).
- Probed dead ends (no build): YC role facets (ignored server-side), PeakXV
  careers and Cutshort listings (JS shells), Getro anchors (empty).
- Open policy calls for Daksh: revisit the Internshala exclusion (biggest
  India internship volume), and nothing else. LinkedIn Jobs stays prohibited.

## Amendment 2026-09-11 (Daksh Jain): Hunter.io contact finder

- Finder runs only when a record has no usable contact and a real company
  domain; verifier stays OFF unless Daksh explicitly enables it.
- Hunter results are found leads, never verified: confidence high requires a
  deliverable verification plus score >= 90, and guessed/pattern emails are
  never exposed. Generic and excluded mailboxes reuse the existing filters.
- Monthly search/verification caps plus per-domain monthly cache bound the free
  tier; quota is cross-checked against Hunter's free /account endpoint.
- Key lives in `HUNTER_API_KEY` (local .env, Modal hunt secrets). No key means
  the finder quietly skips; contacts stay manual.
- Provider seam is ready for Apollo/Snov trials, which need Daksh's keys plus
  a separate approval each. Not built now.

## Activation boundaries

- No additional paid actor call until fixture normalization passes.
- No frontend deployment, branch push, or scheduler retirement without the
  corresponding rollout authorization and canary evidence.
- The original standalone workspace remains available as an archive until the
  migrated state-writing collection and idempotent delivery are proven.
