# Brief: problem-led outreach — real problems, prototype prompts, real contacts

Date: 2026-09-12/13
Approved by: Daksh Jain (plan approved and refined across several
clarifying rounds in session; full detail, evidence, and phase-by-phase
design in `C:\Users\daksh\.claude\plans\i-want-you-to-ethereal-sloth.md`).

## Trigger

Two follow-on requests after the 2026-09-12 digest fix:

1. The funding section of the digest names companies but never produces
   a problem. Root cause (confirmed, not guessed): `pipeline.py` calls
   `research_funding_event(event, allow_llm=False)`, which always returns
   a hardcoded stub with an empty `problem_hypothesis`; funding events
   never get a `company_url`, so no site evidence is ever fetched; and
   company names are raw regex-extracted headline fragments, sometimes
   naming multiple companies at once ("From Pixxel To Swish — Indian
   Startups") and sometimes mojibaked.
2. Daksh wants the pipeline to actually find a real problem at a company,
   generate a paste-ready Claude Code prompt that builds a working
   prototype for that problem, and hand him a real contact (email +
   LinkedIn profile where provenanced) so his outreach is: read email,
   paste prompt, build demo, send manually. Three specific target
   companies (Emergent, Lyzr AI, AEOS) are currently invisible to the
   pipeline for three different structural reasons (unsupported ATS,
   Teamtailor with no adapter, no funding event/board at all since it's
   bootstrapped) and need dedicated coverage.

## Scope

Full detail is in the plan file — this brief exists to satisfy this
workspace's own "brief before implementation" rule; the plan file is the
working spec, organized as Phases 1 through 8.

## Decisions already made (do not re-ask)

- Problem sources: company-owned surfaces, Reddit + Hacker News, app/
  extension store reviews, public X/LinkedIn posts via already-approved
  Apify actors.
- Generated prompt produces a runnable prototype spec, not an
  architecture essay.
- No sector filter on the problem-led track; consumer/AI/tech get a
  ranking bonus, not a gate.
- Problem-led track's automatic input is recently funded companies (any
  sector) plus three named watchlist companies (Emergent, Lyzr, AEOS)
  that get deep research every run regardless of funding or open roles.
- Role breadth for the internship-matching track is unchanged.
- `/my-hunt` ships via merging `personal-hunt-migration` to `main` —
  **done 2026-09-12**, deployed to
  `https://rise-web-kappa.vercel.app/my-hunt`.
- Cold email, LinkedIn connection note, and LinkedIn message follow the
  humanizer ruleset, encoded as a deterministic validator (the Modal
  runtime cannot invoke a Claude Code skill).
- All implementation subagents run on Haiku.
- Ship order: Phase 8 (done) → Phases 1-3 → Phase 6 → Phases 4, 5, 7.

## Definition of done

Per this workspace's CLAUDE.md: tests pass, a real (not fixture) run is
inspected, credential-bound checks run since Bedrock/Gmail/Apify
credentials exist, failures are written down, and the plan's own
verification table is filled in with numbers from an actual cloud run.
The plan's stated acceptance test for the whole effort: paste a generated
prompt into a real Claude Code session and confirm it produces a runnable
prototype without needing invented facts.
