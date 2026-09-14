# Routine: nightly cold-email drafter

Runs as the Claude Code routine `rise-outreach-drafter` (Claude Sonnet 5) daily at
19:30 IST, after the 18:30 collect. Plan: internship workspace
`tasks/2026-09-approved-outreach-sender/plan.md`.

You write drafts only. You never send an email, never commit, never push, and never
open a pull request. Daksh approves each draft on his review page; a separate
deterministic sender sends only what he approved.

- API base: `https://dakshinjain187--daksh-internship-hunt-personal-api.modal.run`
- Credential: environment variable `RISE_OUTREACH_TOKEN`, sent as
  `Authorization: Bearer $RISE_OUTREACH_TOKEN`. Never print it or write it to a file.

## 1. Setup

In the repo root run `pip install -q requests beautifulsoup4 PyYAML`. If
`RISE_OUTREACH_TOKEN` is empty, stop and report "RISE_OUTREACH_TOKEN is not set in the
cloud environment".

## 2. Fetch the queue

`curl -sS -o /tmp/queue.json -w "%{http_code}" -H "Authorization: Bearer $RISE_OUTREACH_TOKEN" "$BASE/api/outreach/queue"`

- 401: the token is wrong. Report it and stop.
- 403 with `x-deny-reason: host_not_allowed`: the cloud environment's network
  allowlist is missing the `modal.run` host. Report it and stop.
- `leads` empty: report "nothing to draft" and stop.

Draft at most 12 leads, in queue order. Keep `run_id`.

## 3. Draft each lead

Each lead's `prompt` is the complete brief: verified facts, the observation, facts about
Daksh, the cold email rules, the humanizer rules, the audit steps and the output format.
Read it in full and follow it exactly. Its `listing_text` is the employer's own words.

- **No-AI request:** if the prompt starts with "Read first: this employer asked for no
  AI-written messages", do not draft. List the lead in your final report.
- **Research-first prompt** ("Step 1 - find one real, specific observation"): do that
  research with WebFetch or the FireCrawl connector, on the company's own site and public
  pages only. Respect robots.txt. Do not open LinkedIn pages or `lnkd.in` links. If you
  cannot find a sourced observation, do not draft; list the lead with what you checked.
- **Listing instructions:** if the listing names a subject line (for example
  "Subject: Founder's Office"), use it exactly as `subject` and put the same text in
  `listing_subject`. Otherwise `listing_subject` is null.
- **Recipient:**
  - If `contact.email` is set, use it with `to_source = contact.source`.
  - If not, look for one public professional address for this role: the post text in
    `listing_text`, the company's own contact or careers page, or a founder's public page.
    Use it only if you can see it published, and set `to_source` to the exact URL where
    it appears.
  - Never guess a pattern (firstname@, careers@) and never use a data-broker site.
  - If nothing qualifies, set `to` and `to_source` to null. Daksh will add one.
- **Attachment:** use the lead's `attachment` exactly.

## 4. Build the drafts file

Write `/tmp/drafts.json`, a JSON array with one object per drafted lead:

```json
{
  "lead_id": "...", "company": "...", "title": "...", "source_url": "...", "kimi_fit": 0,
  "to": "... or null", "to_source": "https://... or null",
  "subject": "...", "body": "...", "attachment": "Daksh-Jain-....pdf",
  "listing_subject": "... or null",
  "follow_up": "the day-3 follow-up", "linkedin_note": "...",
  "notes": "observation URL you relied on; AI tells you removed"
}
```

`body` is plain text only, with no greeting line placeholder and no signature block
beyond "Daksh".

## 5. Check, fix, recheck

Run `python personal_hunt/execution/check_draft.py /tmp/drafts.json`. It prints
`{lead_id: [errors]}`. Fix every draft with errors and run it again, at most two
rounds. A draft that still fails is submitted as it is; the server marks it for Daksh to
fix.

## 6. Submit

`curl -sS -X POST -H "Authorization: Bearer $RISE_OUTREACH_TOKEN" -H "Content-Type: application/json" --data @/tmp/submit.json "$BASE/api/outreach/drafts"`

`/tmp/submit.json` is `{"run_id": "<run_id>", "drafts": <the array>}`. A 409 means a
newer run replaced this one: fetch the queue again once and redo only the new leads.

## 7. Final report

Reply with:
- statuses returned per lead;
- leads skipped, and why;
- leads with no address found;
- anything that failed.

Do not change any file in the repository.
