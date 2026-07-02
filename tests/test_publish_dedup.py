"""Unit tests for the publisher's dedup + parsing helpers.

Skipped automatically if the Google API client isn't installed (e.g. a slim
local env); CI installs the full requirements so these always run there.
"""

import pytest

pytest.importorskip("googleapiclient")

import publish_to_sheets as pub  # noqa: E402


class TestParseStipendInt:
    def test_k(self):
        assert pub._parse_stipend_int("10k") == 10000

    def test_lakh(self):
        assert pub._parse_stipend_int("5L") == 500000

    def test_blank(self):
        assert pub._parse_stipend_int("") == ""

    def test_words(self):
        assert pub._parse_stipend_int("unpaid") == ""


class TestNormalizeCompany:
    def test_strips_suffixes(self):
        assert pub._normalize_company("Acme Technologies Pvt. Ltd.") == "acme"

    def test_case_and_punct_insensitive(self):
        assert pub._normalize_company("ACME, Inc.") == pub._normalize_company("acme inc")


class TestStandardizeRole:
    def test_software_bucket(self):
        assert pub.standardize_role_for_dedup("Senior Backend Developer Intern") == "software"

    def test_data_bucket(self):
        assert pub.standardize_role_for_dedup("Machine Learning Intern") == "data"

    def test_marketing_bucket(self):
        assert pub.standardize_role_for_dedup("SEO & Social Media Intern") == "marketing"


class TestDedupKeys:
    def test_url_is_a_key(self):
        keys = pub.generate_dedup_keys({"url": "https://x.com/p/1", "company": "Acme", "title": "SDE Intern"})
        assert "https://x.com/p/1" in keys

    def test_company_role_key(self):
        keys = pub.generate_dedup_keys({"company": "Acme Pvt Ltd", "title": "Backend Developer Intern"})
        assert any(":software" in k for k in keys)

    def test_same_company_role_collides(self):
        a = pub.generate_dedup_keys({"company": "Acme", "title": "Backend Intern"})
        b = pub.generate_dedup_keys({"company": "Acme", "title": "Backend Developer Intern"})
        assert set(a) & set(b)
