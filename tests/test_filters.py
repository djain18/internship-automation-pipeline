"""Unit tests for the deterministic post filters (execution/filters.py).

These pin the rules that define the product: scam rejection, personal-story
rejection, hiring-intent detection, and India-eligibility.
"""

import filters


class TestScam:
    def test_registration_fee_is_scam(self):
        assert filters.is_scam("Hiring interns! Pay a registration fee of 500 to join.")

    def test_earn_daily_typing_is_scam(self):
        assert filters.is_scam("Simple typing job, earn daily from home, no investment!")

    def test_guaranteed_placement_is_scam(self):
        assert filters.is_scam("100% genuine internship with guaranteed placement.")

    def test_real_post_is_not_scam(self):
        assert not filters.is_scam(
            "We're hiring a Backend Intern in Bangalore. Apply at careers@acme.com"
        )


class TestPersonalStory:
    def test_open_to_work_is_story(self):
        assert filters.is_personal_story("I am looking for a marketing internship, open to work!")

    def test_celebration_is_story(self):
        assert filters.is_personal_story("Excited to announce I officially a Google intern now!")

    def test_job_opening_is_not_story(self):
        assert not filters.is_personal_story("Hiring Data Science interns, apply now.")


class TestHiringIntent:
    def test_hiring_keyword(self):
        assert filters.has_hiring_intent("We are hiring for multiple roles.")

    def test_intern_keyword(self):
        assert filters.has_hiring_intent("Software intern position available.")

    def test_random_text_has_no_intent(self):
        assert not filters.has_hiring_intent("Just had a great lunch with the team today.")


class TestBlacklist:
    def test_gao_is_blacklisted(self):
        assert filters.is_blacklisted_company("GAO Tek Inc.")

    def test_normal_company_ok(self):
        assert not filters.is_blacklisted_company("Zerodha")


class TestIndiaEligibility:
    def test_indian_city_location(self):
        assert filters.is_india_eligible("Bangalore", "Hiring interns")

    def test_pan_india(self):
        assert filters.is_india_eligible("Pan India", "")

    def test_foreign_location_rejected(self):
        assert not filters.is_india_eligible("London, UK", "Hiring interns")

    def test_remote_with_india_context_accepted(self):
        assert filters.is_india_eligible("Remote", "Open to Indian candidates across India.")

    def test_remote_without_india_context_rejected(self):
        assert not filters.is_india_eligible("Remote", "Global team, work from anywhere.")

    def test_dual_office_with_india_accepted(self):
        # Location names a foreign city but also India → not rejected outright.
        assert filters.is_india_eligible("Dubai / India", "")


class TestClassify:
    def test_full_real_post_kept(self):
        keep, reason = filters.classify(
            "We're hiring a Frontend Intern! Apply at jobs@acme.in",
            location="Mumbai",
            company="Acme",
        )
        assert keep and reason == "ok"

    def test_scam_dropped_with_reason(self):
        keep, reason = filters.classify(
            "Earn daily! Registration fee 300.", location="Delhi"
        )
        assert not keep and reason == "scam"

    def test_foreign_dropped_with_reason(self):
        keep, reason = filters.classify(
            "Hiring interns, apply now", location="New York, USA"
        )
        assert not keep and reason == "not_india_eligible"
