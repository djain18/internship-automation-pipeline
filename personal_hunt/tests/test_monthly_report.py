from monthly_report import build_monthly_report


def test_monthly_report_shows_raw_counts_and_sample_status_without_weights() -> None:
    rows = [{
        "source": "greenhouse", "role_family": "operations", "contact_type": "named",
        "strategy_id": "operations_workflow_audit", "sent_at": "2026-09-01",
        "reply_outcome": "positive", "interview_outcome": "scheduled",
    }]
    report = build_monthly_report(rows)
    bucket = report["groups"]["source"]["greenhouse"]
    assert bucket == {
        "records": 1, "sends": 1, "replies": 1, "interviews": 1,
        "sample_status": "insufficient_sample",
    }
    assert report["scoring_weights_changed"] is False
