"""Unit tests for the scraper's regex extraction helpers.

Skipped automatically if apify-client isn't installed locally; CI runs them.
"""

import pytest

pytest.importorskip("apify_client")

import scrape_linkedin_posts as scr  # noqa: E402


class TestParsePostedTime:
    def test_hours(self):
        assert scr.parse_posted_time("5h") == 5

    def test_days(self):
        assert scr.parse_posted_time("3d") == 72

    def test_weeks(self):
        assert scr.parse_posted_time("2w") == 2 * 24 * 7

    def test_minutes_is_zero(self):
        assert scr.parse_posted_time("30m") == 0

    def test_timestamp_wins(self):
        # A ms timestamp for ~now → ~0 hours old.
        import time
        now_ms = int(time.time() * 1000)
        assert scr.parse_posted_time("", now_ms) in (0, 1)

    def test_unparseable_is_none(self):
        assert scr.parse_posted_time("yesterday-ish") is None


class TestExtractEmails:
    def test_finds_email(self):
        assert "jobs@acme.com" in scr.extract_emails_from_text("Apply at jobs@acme.com now")

    def test_ignores_image_files(self):
        assert scr.extract_emails_from_text("see logo@2x.png") == []


class TestExtractLocation:
    def test_city(self):
        assert "Bangalore" in scr.extract_location_from_text("Role based in Bangalore")

    def test_remote(self):
        assert scr.extract_location_from_text("This is a remote role") == "Remote"

    def test_bengaluru_maps_to_bangalore(self):
        assert "Bangalore" in scr.extract_location_from_text("We are in Bengaluru")


class TestExtractApplyLink:
    def test_prefers_form_link(self):
        text = "Read more at https://blog.acme.com and apply at https://forms.gle/abc"
        assert scr.extract_apply_link(text) == "https://forms.gle/abc"

    def test_falls_back_to_first_url(self):
        assert scr.extract_apply_link("visit https://acme.com") == "https://acme.com"

    def test_no_url(self):
        assert scr.extract_apply_link("no links here") == ""


class TestExtractRole:
    def test_software(self):
        assert scr.extract_role("Hiring a backend developer intern") == "Software Developer Intern"

    def test_generic_fallback(self):
        # Clean generic phrasing. NB: the legacy regex matches substrings, so
        # words like "available"/"trainee" (contain "ai") would mis-hit "ML/AI".
        assert scr.extract_role("fresher role open") == "Internship"


class TestStdRoleKey:
    def test_software(self):
        assert scr._std_role_key("Full Stack Developer Intern") == "software"

    def test_finance(self):
        assert scr._std_role_key("Finance Intern") == "finance"
