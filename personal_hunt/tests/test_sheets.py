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


def test_outcomes_are_summarised_per_source_from_human_columns() -> None:
    from sheets import summarize_outcomes

    opportunities = [
        {"id": "opp-1", "source": "linkedin_posts_apify"},
        {"id": "opp-2", "source": "yc_bengaluru"},
        {"id": "opp-3", "source": "yc_bengaluru"},
    ]
    outreach = [
        {"opportunity_id": "opp-1", "send_status": "sent_manually", "reply_outcome": "positive", "interview_outcome": "scheduled"},
        {"opportunity_id": "opp-2", "send_status": "draft_needs_human_review", "sent_at": "2026-09-14", "reply_outcome": "no_reply"},
        {"opportunity_id": "opp-3", "send_status": "draft_needs_human_review"},
    ]
    summary = summarize_outcomes(outreach, opportunities)
    assert (summary["applied"], summary["replied"], summary["interviewed"]) == (2, 1, 1)
    assert summary["by_source"]["linkedin_posts_apify"] == {"applied": 1, "replied": 1, "interviewed": 1}
    assert summary["by_source"]["yc_bengaluru"] == {"applied": 1, "replied": 0, "interviewed": 0}


def test_apply_outcomes_fills_source_yield_and_digest_line() -> None:
    from digest import _cost_section
    from pipeline import apply_outcomes

    run = {"source_yield": [{"source": "yc_bengaluru", "manually_applied": 0, "replied": 0, "interviewed": 0}]}
    apply_outcomes(run, {"applied": 3, "replied": 1, "interviewed": 0, "by_source": {"yc_bengaluru": {"applied": 3, "replied": 1, "interviewed": 0}}})
    assert run["source_yield"][0]["replied"] == 1
    assert run["outcomes"] == {"applied": 3, "replied": 1, "interviewed": 0}
    line = _cost_section(run)
    assert "applied 3, replied 1, interviewed 0" in line
    assert "Replies came from: yc_bengaluru (1)" in line


def test_followups_due_on_day_3_8_14_only_for_unanswered_sends() -> None:
    from datetime import date

    from sheets import summarize_outcomes

    today = date(2026, 9, 20)
    rows = [
        {"opportunity_id": "a", "company": "Kplor", "sent_at": "2026-09-17"},                 # day 3
        {"opportunity_id": "b", "company": "SuprSend", "sent_at": "2026-09-12T10:00:00"},     # day 8
        {"opportunity_id": "c", "company": "Sarvam AI", "sent_at": "2026-09-05"},             # day 15 -> 14 window
        {"opportunity_id": "d", "company": "Replied Co", "sent_at": "2026-09-17", "reply_outcome": "positive"},
        {"opportunity_id": "e", "company": "Too Soon", "sent_at": "2026-09-19"},
        {"opportunity_id": "f", "company": "Bad Date", "sent_at": "next week"},
    ]
    due = summarize_outcomes(rows, [], today)["followups_due"]
    assert [(item["company"], item["day"]) for item in due] == [("Kplor", 3), ("SuprSend", 8), ("Sarvam AI", 14)]


def test_followups_render_in_both_digests() -> None:
    from digest import render_html_digest, _followups_section

    run = {
        "run_date": "2026-09-20", "digest_primary": [], "digest_remote_fallback": [], "primary": [],
        "remote_fallback": [], "source_health": [], "outcomes": {"applied": 2, "replied": 0, "interviewed": 0},
        "followups_due": [{"company": "Kplor", "day": 14, "days_since_sent": 14, "contact_email": "a@kplor.com"}],
    }
    assert "close the loop" in _followups_section(run)
    html_body = render_html_digest(run)
    assert "Follow-ups due today" in html_body
    assert "To date: applied 2" in html_body
