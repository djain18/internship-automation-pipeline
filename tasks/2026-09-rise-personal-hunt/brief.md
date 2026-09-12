# Brief: Rise Private Internship Hunt

Approved: 2026-09-10

## Outcome

Move the proven personal internship-hunt automation into the Rise repository
and operate it as a private feature for `dakshinjain187@gmail.com`, without
changing the public Rise pipeline or subscriber digest.

The private workflow targets Bengaluru onsite/hybrid and India-remote
Founder’s Office/generalist internships plus genuinely cross-functional
operations, growth/GTM, product, and launch roles. AI and consumer/D2C lanes
receive equal opportunity. Applications and prospect outreach remain manual.

## Approved delivery

- Continue using the existing eight-tab personal tracking Sheet.
- Continue using the existing `daksh-internship-hunt` Modal app and volume.
- Collect at 00:30 Asia/Kolkata and send a new-only Gmail HTML digest at 08:00.
- Add a Firebase-authenticated, read-only `/my-hunt` Rise page accessible only
  to the verified primary email.
- Reuse free/public sources first. Run a personal LinkedIn top-up only below
  five deterministic candidates, capped at $0.25/run and $5/month across the
  active Apify account. Never rotate tokens automatically.

## Acceptance decision

Daksh explicitly replaced the earlier seven-consecutive-run shadow gate with a
same-day acceptance gate on 2026-09-10. Activation is allowed after unit and
integration tests, fixture inspection, a live no-send/no-state run, Sheet
sandbox, private API authorization checks, HTML render inspection, and exactly
one authorized Gmail canary pass.

## Non-negotiable boundaries

- No automated applications or prospect sends.
- No LinkedIn Jobs, session scraping, captcha/login/paywall bypass, TLS bypass,
  or automatic Apify account rotation.
- Preserve source URL, access date, confidence, verification state, and the
  observation/inference distinction.
- Preserve existing uncommitted Rise changes.

