"""Unit tests for the API's read-side transforms (api/sheets.py)."""

from datetime import datetime, timezone

import sheets


class TestParseStipend:
    def test_plain_number(self):
        assert sheets._parse_stipend("15000") == 15000

    def test_k_suffix(self):
        assert sheets._parse_stipend("10k") == 10000

    def test_lakh_suffix(self):
        assert sheets._parse_stipend("5L") == 500000

    def test_rupee_with_comma(self):
        assert sheets._parse_stipend("₹5,000/month") == 5000

    def test_non_numeric_is_zero(self):
        assert sheets._parse_stipend("competitive") == 0

    def test_empty_is_zero(self):
        assert sheets._parse_stipend("") == 0


class TestInferCluster:
    def test_software(self):
        assert sheets._infer_cluster("Backend Developer Intern", []) == "Software"

    def test_data_ai(self):
        assert sheets._infer_cluster("Machine Learning Intern", []) == "Data/AI"

    def test_falls_back_to_operations(self):
        assert sheets._infer_cluster("Mystery Intern", []) == "Operations"

    def test_uses_tags(self):
        assert sheets._infer_cluster("Intern", ["Finance"]) == "Finance"

    def test_ai_short_form_matches(self):
        assert sheets._infer_cluster("AI Intern", []) == "Data/AI"

    def test_ml_short_form_matches(self):
        assert sheets._infer_cluster("ML Engineer Intern", []) == "Data/AI"

    def test_fundraising_does_not_false_match_ai(self):
        # "fundraising" contains "ai" as a bare substring — regression test for
        # the word-boundary fix (was miscategorizing this as Data/AI).
        assert sheets._infer_cluster("Fundraising", []) == "Operations"

    def test_training_does_not_false_match_ai(self):
        assert sheets._infer_cluster("Sales Training Intern", []) != "Data/AI"

    def test_email_marketing_does_not_false_match_ai(self):
        # "email" contains "ai" as a bare substring, but this should hit the
        # earlier Marketing check, not Data/AI.
        assert sheets._infer_cluster("Email Marketing Intern", []) == "Marketing"

    def test_ui_short_form_matches(self):
        assert sheets._infer_cluster("UI Designer Intern", []) == "Design"

    def test_talent_acquisition_does_not_false_match_ui(self):
        # "Acquisition" contains "ui" as a bare substring — should hit HR
        # (via "talent"), not Design.
        assert sheets._infer_cluster("Talent Acquisition", []) == "HR"

    def test_equity_analyst_does_not_false_match_ui(self):
        # "Equity" contains "ui" as a bare substring — should hit Finance.
        assert sheets._infer_cluster("Finance Equity Analyst", []) == "Finance"

    def test_recruitment_tag_does_not_false_match_ui(self):
        # "Recruitment" contains "ui" as a bare substring.
        assert sheets._infer_cluster("HR Associate", ["Recruitment"]) == "HR"

    def test_founders_office(self):
        assert sheets._infer_cluster("Founder's Office Intern", []) == "Founder's Office"

    def test_chief_of_staff_matches_founders_office(self):
        assert sheets._infer_cluster("Chief of Staff Intern", []) == "Founder's Office"

    def test_forward_deployed_engineer(self):
        assert sheets._infer_cluster("Forward Deployed Engineer Intern", []) == "Forward Deployed"

    def test_solutions_engineer_matches_forward_deployed(self):
        assert sheets._infer_cluster("Solutions Engineer", []) == "Forward Deployed"

    def test_ai_automation_engineer(self):
        assert sheets._infer_cluster("AI Automation Engineer Intern", []) == "AI Automation"

    def test_ai_agent_matches_ai_automation_not_data_ai(self):
        # Should hit the more specific AI Automation bucket, not the broader
        # Data/AI word-boundary catch-all checked further down.
        assert sheets._infer_cluster("AI Agent Engineer", []) == "AI Automation"

    def test_digital_marketing_with_video_tag_does_not_false_match_design(self):
        # Surfaced by a real production listing: "Video Editing" is a common
        # social-media-content skill tag, not a design signal — Marketing's
        # explicit "marketing" keyword in the title should win.
        assert sheets._infer_cluster("Digital Marketing Intern", ["Digital Marketing", "Video Editing", "Content Creation"]) == "Marketing"

    def test_plain_ai_intern_still_matches_data_ai(self):
        # No automation-specific keyword present — regression guard that the
        # new AI Automation branch doesn't over-match generic AI postings.
        assert sheets._infer_cluster("AI Intern", []) == "Data/AI"


class TestScore:
    def test_score_within_bounds(self):
        for hours in (0, 12, 48, 200):
            for stipend in (0, 5000, 200000):
                s = sheets._score(hours, stipend)
                assert 50 <= s <= 99


class TestHoursAgo:
    def test_recent_date_is_small(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert sheets._hours_ago(today) <= 24

    def test_blank_defaults_to_24(self):
        assert sheets._hours_ago("") == 24


class TestRowToListing:
    def _row(self, posted_date="", date_added=""):
        # 19 columns A–S
        return [
            "Backend Intern", "Onsite", "Full-time", "Build APIs", "10000",
            "3 months", "Fresher", "Bangalore", "2026-08-01", "Engineering, Python",
            "Acme Corp", "Recruiter Name", "https://linkedin.com/posts/x",
            "https://acme.com/apply", "jobs@acme.com", date_added,
            "Backend Intern, API Intern", "Software, Data", posted_date,
        ]

    def test_basic_mapping(self):
        listing = sheets._row_to_listing(self._row(), 0)
        assert listing["title"] == "Backend Intern"
        assert listing["org"] == "Acme Corp"
        assert listing["cluster"] == "Software"
        assert listing["stipend"] == 10000
        assert listing["id"].startswith("sh-")

    def test_posted_date_drives_freshness_over_date_added(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Row added long ago, but the post itself is fresh today.
        listing = sheets._row_to_listing(
            self._row(posted_date=today, date_added="2020-01-01 09:00"), 0
        )
        assert listing["hoursAgo"] <= 24

    def test_missing_posted_date_uses_date_added(self):
        listing = sheets._row_to_listing(
            self._row(posted_date="", date_added="2020-01-01 09:00"), 0
        )
        # 2020 is far in the past → large hoursAgo, definitely not "fresh".
        assert listing["hoursAgo"] > 24
