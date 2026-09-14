# Internship Hunt Automation

## Safe local run

    python execution/pipeline.py --fixtures

Useful options:

    --input-json PATH       run against a human-reviewed JSON list
    --live                  fetch enabled public source adapters
    --publish-sheets        upsert configured Google Sheet
    --send-digest           send only Daksh's self-digest
    --digest-latest         render/send the latest pointer-verified live run
    --run-date YYYY-MM-DD   deterministic date for tests/backfills
    --dry-run               no Sheets, Gmail, or opportunity-state writes
    --no-state              skip opportunity/run state (delivery ledger remains safe)

The default does not access the network, Sheets, Bedrock, Gmail, or Modal.
Production actions require explicit flags and environment variables.

## Environment variables

- INTERNSHIP_SHEET_ID
- GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE
- GOOGLE_OAUTH_TOKEN_JSON or GOOGLE_OAUTH_TOKEN_FILE
- GMAIL_TOKEN_JSON or GMAIL_TOKEN_FILE, and GMAIL_DIGEST_TO
- ENABLE_BEDROCK, AWS_REGION, BEDROCK_EXTRACTION_MODEL_ID,
  BEDROCK_RESEARCH_MODEL_ID
- PUBLIC_RESEARCH_PROVIDER (defaults to free `source_evidence`; set to
  `firecrawl` only with explicit credit approval) and optional FIRECRAWL_API_KEY
- APIFY_TOKEN (actors remain individually disabled until contract-tested)
- ENABLE_SELF_DIGEST (default false; authorizes only Daksh's self-email)

No variable enables prospect sending because that capability does not exist.

The Modal app defaults to SHADOW_MODE=true and the separate self-digest flag is
off. At 23:00 Asia/Kolkata it collects, scores with pinned Kimi K2.5, writes the
recoverable artifact, and publishes Sheets; at 08:00 it retries only the latest
live digest. Enabling `ENABLE_SELF_DIGEST` still permits only one idempotent
message per live run ID to `dakshinjain187@gmail.com`. Keep `SHADOW_MODE=true`
until the changed v2 behavior completes seven accepted executions.

Internships are strictly seven days old or newer, deterministically score at
least 70, then must pass Kimi fit >=70, relevant=true, and spam=false. Funding
is secondary: 0–15 days primary, 16–30 days visibly labeled, never older.

Kimi scoring contract (2026-09-14): the model sees leads as `1..N`, never real
ids. A reply that is unusable or misses leads is retried once and the better
attempt kept. Leads still without a verdict fail closed one by one (status
`partial`, digest still sent). If scoring fails outright, the 08:30 delivery
sends the deterministic shortlist marked `[UNSCORED]` in the subject and both
bodies, capped at `daily_target`, and does not mark those leads as sent.

