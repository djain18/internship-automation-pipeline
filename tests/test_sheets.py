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
