# Brief: fix silent no-send digest + empty LinkedIn funnel

Date: 2026-09-12
Approved by: Daksh Jain (plan approved in session; see
`C:\Users\daksh\.claude\plans\i-want-you-to-ethereal-sloth.md` for full
detail, evidence and verification steps).

## Trigger

No digest email arrived at 08:30 IST on 2026-09-12. Investigation of the
deployed Modal app and its volume found two independent, confirmed root
causes (not guessed):

1. `_send_once()` in `personal_hunt/execution/pipeline.py` silently
   returns `digest_skipped_no_new_matches` and sends nothing when the
   day's only match was already emailed on a previous day. The
   verification tray and funding sections are discarded along with it,
   even though they don't depend on "new" opportunities.
2. The paid Apify LinkedIn source (`linkedin_posts_apify`) returned 100
   posts; 99 were rejected for `missing_required_identity_or_source`
   because the actor returns post text, not structured
   company/title/location. The existing LLM repair step
   (`extract_linkedin_hiring_fields`) is hardcoded to attempt only 10
   posts per run (`LINKEDIN_EXTRACTION_LIMIT = 10` in
   `execution/llm_rank.py`), while 76 of the 99 posts met its own
   candidate predicate. A same-day, exact-match Founder's Office post
   (Auraaison) was discarded purely because it was never parsed.

## Scope

Fix both. Do not loosen `hard_exclusions()` or any deterministic scoring
gate. Do not add a new paid dependency. Full design and line-level detail
is in the approved plan file referenced above — this brief exists to
satisfy this workspace's "brief before implementation" rule; the plan
file is the working spec.

## Decisions already made (do not re-ask)

- Empty-match days still send an email (Daksh's explicit choice).
- Verification required today, before shipping further: a real send to
  `dakshinjain187@gmail.com` after deploy (Daksh's explicit choice), not a
  wait for tomorrow's cron.
- All implementation subagents run on the Haiku model.
- Ship Part A (always-send) before Part B (LinkedIn extraction), as two
  separate commits.

## Definition of done

Matches this repo's own CLAUDE.md "definition of done": tests pass, a
real (not fixture) run is inspected, credential-bound checks run since
Gmail/Bedrock credentials exist, failures are written down, and the
verification table in the plan file is filled in with real numbers from
an actual cloud run — not asserted from memory.
