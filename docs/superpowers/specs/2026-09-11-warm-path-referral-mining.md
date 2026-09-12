# Warm-Path Referral Mining (spec — no implementation yet)

Status: draft for Daksh's approval, 2026-09-11. Nothing here runs until Daksh
approves the contact sources below. Referrals convert far better than cold
applies; the pipeline currently has zero warm-path coverage.

## Privacy principles (non-negotiable)

- The machine never logs into, scrapes, or syncs Daksh's LinkedIn, Gmail,
  WhatsApp, or any personal account. No session reuse, no contact harvesting.
- Every contact record enters only via an explicit Daksh-provided file
  (LinkedIn connections CSV export, pasted alumni list, event attendee list).
  Each file is consent-scoped: used only for internship referrals, never
  shared, never emailed automatically.
- Storage is local/Modal volume only, same as pipeline state. No contact data
  in git, Sheets, digests, or API responses beyond what Daksh already approved
  for outreach drafts.

## Data model (proposed)

- `referral_person`: id, name, current_company, role, relationship
  (classmate / senior / ex-colleague / event contact), source_file, added_date.
- `referral_link`: person -> pipeline company (exact normalized-company match
  only, same rule as company provenance) or weekly target.
- Links surface in two places: the opportunity's outreach draft gains a
  `referral_ask` variant ("X, a <relationship> at <company>, could intro…"),
  and the Monday weekly-target section lists which targets have a warm path.

## Matching rules

- Exact normalized company match only. No fuzzy employer guessing.
- One referral ask per person per 30 days (machine-enforced from Sheet
  `sent_at`), to protect relationships. Asks are drafts; Daksh sends manually.
- A referral ask never replaces the direct application draft; it is an
  additional option in the same outreach record.

## Approval gates

1. Daksh approves this spec.
2. Daksh provides the first contact file and names its scope.
3. Implementation lands behind the same test/review bar as the pipeline.
4. First digest containing a referral ask is inspected before any send.

## Metrics

- Warm intros requested, intros granted, referrals converting to interview.
- Reported in the monthly offline report as a new `contact_type=referred`
  dimension (needs 10 sends before any weight discussion, per existing rule).

## Rollout

Spec approval -> contact file -> implementation slice -> fixture test with a
synthetic graph -> one inspected digest -> live. No paid services, no new
credentials, no external calls at any step.
