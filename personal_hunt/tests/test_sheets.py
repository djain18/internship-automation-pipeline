from sheets import TAB_SCHEMAS, merge_existing_row, rows_from_run
from validate_tracking_sheet import validate_headers


def test_all_system_of_record_tabs_exist() -> None:
    assert set(TAB_SCHEMAS) == {
        "Companies", "Opportunities", "Outreach", "Artifacts",
        "Runs", "Source Health", "Config",
        "Funding Signals",
    }


def test_rows_keep_outreach_manual() -> None:
    run = {
        "run_id": "run_1",
        "run_date": "2026-09-08",
        "status": "complete",
        "raw_count": 1,
        "eligible_count": 1,
        "completed_at": "2026-09-08T00:00:00+00:00",
        "source_health": [],
        "remote_fallback": [],
        "primary": [
            {
                "id": "opp_1",
                "company": "Test",
                "outreach": {
                    "send_status": "draft_needs_human_review",
                    "email_subject": "founder office idea",
                    "claude_prompt": "# Test: draft the outreach email",
                },
                "selected_contact": {},
            }
        ],
    }
    rows = rows_from_run(run)
    assert rows["Outreach"][0]["send_status"] == "draft_needs_human_review"
    assert rows["Outreach"][0]["next_action"] == "human_review"
    # draft's own key is "email_subject" -- the Sheet column read "subject"
    # from a key ("subject") neither draft function has ever emitted, which
    # left this column silently blank on every real run.
    assert rows["Outreach"][0]["subject"] == "founder office idea"
    assert rows["Outreach"][0]["claude_prompt"] == "# Test: draft the outreach email"


def test_existing_human_owned_values_survive_machine_upsert() -> None:
    headers = ["id", "company", "send_status", "mailsuite_status", "next_action"]
    existing = ["outreach_1", "Old", "sent", "opened", "follow_up_due"]
    merged = merge_existing_row(
        "Outreach",
        headers,
        existing,
        {
            "id": "outreach_1",
            "company": "Updated",
            "send_status": "draft_needs_human_review",
            "mailsuite_status": "not_sent",
            "next_action": "human_review",
        },
    )
    assert merged == ["outreach_1", "Updated", "sent", "opened", "follow_up_due"]


def test_outreach_outcomes_and_human_strategy_survive_upsert() -> None:
    headers = ["id", "sent_at", "reply_outcome", "interview_outcome", "strategy_id", "human_quality_rating"]
    existing = ["outreach_1", "2026-09-11", "positive", "scheduled", "custom_strategy", "5"]
    merged = merge_existing_row("Outreach", headers, existing, {
        "id": "outreach_1", "strategy_id": "growth_funnel_teardown"
    })
    assert merged == existing


def test_sheet_validator_accepts_append_only_migration_order() -> None:
    result = validate_headers(
        ["id", "company", "llm_rank", "status"],
        ["id", "company", "status", "llm_rank", "human_notes"],
    )
    assert result["valid"]
    assert result["extra_headers"] == ["human_notes"]


def test_sheet_validator_rejects_missing_or_duplicate_required_headers() -> None:
    result = validate_headers(
        ["id", "company", "status"],
        ["id", "company", "company"],
    )
    assert not result["valid"]
    assert result["missing_headers"] == ["status"]
    assert result["duplicate_headers"] == ["company"]
