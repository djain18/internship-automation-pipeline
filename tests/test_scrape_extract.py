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
        # Finance/HR/Legal share one role_taxonomy track — they compete for the
        # same nightly quota slot, so they dedup together too.
        assert scr._std_role_key("Finance Intern") == "finance_hr_legal"

    def test_matches_publish_side_bucket(self):
        # The scraper's cross-query dedup and publish_to_sheets' sheet dedup
        # must agree, or a post skipped in one place reappears in the other.
        import publish_to_sheets as pub
        for title in ("Full Stack Developer Intern", "AI Automation Intern",
                      "Founder's Office Intern", "SEO Intern"):
            assert scr._std_role_key(title) == pub.standardize_role_for_dedup(title)


class TestApifyBudgetGuard:
    """Apify bills per RESULT and the account carries a hard monthly cap. A
    2026-08-23 run fanned out 118 queries with no run-level ceiling, burned the
    remaining monthly budget inside the first ~30, and then logged 100+
    identical 'Monthly usage hard limit exceeded' failures while publishing
    nothing. These guard that."""

    def test_per_track_budget_splits_the_run_budget(self):
        per_track = scr._per_track_budget(12)
        assert per_track * 12 <= scr.MAX_RESULTS_PER_RUN
        # Every track must get a usable share, not a token one.
        assert per_track >= 20

    def test_per_track_budget_has_a_floor(self):
        # Many tracks must not divide the share down to nothing.
        assert scr._per_track_budget(500) >= 20

    def test_per_track_budget_survives_zero_tracks(self):
        assert scr._per_track_budget(0) >= 20

    def test_run_budget_is_affordable(self):
        # The whole point: one run must not cost more than the agreed ~$1.40.
        cost = scr.MAX_RESULTS_PER_RUN * scr.APIFY_USD_PER_RESULT
        assert cost <= 1.50, f"a single run would cost ${cost:.2f}"

    def test_budget_check_blocks_when_exhausted(self, monkeypatch):
        class _Resp:
            @staticmethod
            def json():
                return {"data": {"current": {"monthlyUsageUsd": 5.0},
                                 "limits": {"maxMonthlyUsageUsd": 5.0}}}
        monkeypatch.setenv("APIFY_API_TOKEN", "stub")
        monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
        ok, msg = scr.check_apify_budget()
        assert ok is False
        assert "EXHAUSTED" in msg

    def test_budget_check_allows_when_funded(self, monkeypatch):
        class _Resp:
            @staticmethod
            def json():
                return {"data": {"current": {"monthlyUsageUsd": 1.0},
                                 "limits": {"maxMonthlyUsageUsd": 5.0}}}
        monkeypatch.setenv("APIFY_API_TOKEN", "stub")
        monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
        ok, _ = scr.check_apify_budget()
        assert ok is True

    def test_budget_check_fails_open_on_network_error(self, monkeypatch):
        # A flaky limits endpoint must not block an otherwise-funded run.
        def _boom(*a, **k):
            raise RuntimeError("network down")
        monkeypatch.setenv("APIFY_API_TOKEN", "stub")
        monkeypatch.setattr("requests.get", _boom)
        ok, msg = scr.check_apify_budget()
        assert ok is True
        assert "proceeding" in msg


class TestPostedLimitVocabulary:
    """harvestapi validates postedLimit against a fixed vocabulary and rejects
    the whole query otherwise. "7d" was rejected outright, silently killing
    every scarce-track query in the 2026-08-23 run."""

    ALLOWED = {"any", "1h", "24h", "week", "month", "3months", "6months", "year"}

    def test_scarce_and_abundant_limits_are_valid(self, monkeypatch):
        monkeypatch.delenv("SCRAPE_POSTED_LIMIT", raising=False)
        for scarce in (True, False):
            params = scr._build_actor_input(
                "harvestapi/linkedin-post-search", "q", {}, scarce=scarce)
            assert params["postedLimit"] in self.ALLOWED

    def test_scarce_window_is_wider_than_abundant(self, monkeypatch):
        monkeypatch.delenv("SCRAPE_POSTED_LIMIT", raising=False)
        mk = lambda sc: scr._build_actor_input(
            "harvestapi/linkedin-post-search", "q", {}, scarce=sc)["postedLimit"]
        assert mk(True) == "week"
        assert mk(False) == "24h"


class TestRunResultShape:
    """apify-client returns a plain dict on 2.x but a `Run` model object on 3.x.

    requirements.txt pinned only `apify-client>=1.0.0`, so Modal's image resolved
    a newer major than local dev. Every query in the 2026-09-04 cloud run died on
    `'Run' object has no attribute 'get'` — the actors ran and were BILLED, but
    the dataset was never read. 38/38 queries, full cost, zero posts.
    """

    class _RunModel:
        """Stand-in for the 3.x Run model: attributes, snake_case, no .get()."""
        def __init__(self, id="run1", status="SUCCEEDED", default_dataset_id="ds1"):
            self.id = id
            self.status = status
            self.default_dataset_id = default_dataset_id

    def test_reads_dict_shape(self):
        run = {"id": "run1", "status": "SUCCEEDED", "defaultDatasetId": "ds1"}
        assert scr._run_field(run, "status") == "SUCCEEDED"
        assert scr._run_field(run, "defaultDatasetId") == "ds1"
        assert scr._run_field(run, "id") == "run1"

    def test_reads_object_shape(self):
        run = self._RunModel()
        assert scr._run_field(run, "status") == "SUCCEEDED"
        assert scr._run_field(run, "defaultDatasetId") == "ds1"
        assert scr._run_field(run, "id") == "run1"

    def test_missing_field_returns_default(self):
        assert scr._run_field({}, "defaultDatasetId") is None
        assert scr._run_field(self._RunModel(), "nopeNotHere", "fb") == "fb"

    def test_none_run_returns_default(self):
        assert scr._run_field(None, "status") is None

    def test_object_shape_actually_yields_items(self, monkeypatch):
        """End-to-end guard: the object shape must reach iterate_items(), not raise."""
        captured = {}

        class _Dataset:
            def iterate_items(self):
                return iter([{"post": 1}, {"post": 2}])

        class _Actor:
            def call(self, run_input=None):
                return TestRunResultShape._RunModel()

        class _Client:
            def __init__(self, token):
                pass

            def actor(self, actor_id):
                return _Actor()

            def dataset(self, dataset_id):
                captured["dataset_id"] = dataset_id
                return _Dataset()

        monkeypatch.setenv("APIFY_API_TOKEN", "tok")
        monkeypatch.setattr(scr, "ApifyClient", _Client)

        items = scr.run_apify_actor("harvestapi/linkedin-post-search", {})
        assert len(items) == 2
        assert captured["dataset_id"] == "ds1"

    def test_missing_dataset_id_raises_rather_than_silently_returning_empty(
            self, monkeypatch):
        """A billed run whose dataset can't be located must be loud, not a quiet 0."""
        class _Actor:
            def call(self, run_input=None):
                return {"id": "run1", "status": "SUCCEEDED"}  # no dataset id

        class _Client:
            def __init__(self, token):
                pass

            def actor(self, actor_id):
                return _Actor()

        monkeypatch.setenv("APIFY_API_TOKEN", "tok")
        monkeypatch.setattr(scr, "ApifyClient", _Client)

        with pytest.raises(Exception, match="dataset"):
            scr.run_apify_actor("harvestapi/linkedin-post-search", {})
