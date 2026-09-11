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

## Implementation slices

1. Stabilize Rise ownership and record the externally initiated HarvestAPI run.
2. Repair LinkedIn-post normalization and add a paid-source CLI gate.
3. Move Kimi/research behind cheap gates and cache by content/prompt/model.
4. Add public Greenhouse, Lever, Ashby, and Workable watchlist adapters.
5. Add company provenance, weekly targets, outreach strategies, outcomes, and
   source/cost reporting.
6. Verify fixtures, both Python suites, frontend tests/build, and safe dry runs.

## Activation boundaries

- No additional paid actor call until fixture normalization passes.
- No frontend deployment, branch push, or scheduler retirement without the
  corresponding rollout authorization and canary evidence.
- The original standalone workspace remains available as an archive until the
  migrated state-writing collection and idempotent delivery are proven.
