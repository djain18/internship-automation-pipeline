"""Unit tests for execution/quality_filter.py — the single source of truth for
the anti-spam + location policy used by scrape_linkedin_posts.py.

Focused on location_decision(), since the 2026-08-21 policy change widened
onsite acceptance from a 12-city list to all of India.
"""

import quality_filter as qf


class TestLocationDecisionAcceptedCities:
    def test_bengaluru_accepted(self):
        accept, mode, _ = qf.location_decision("Bengaluru", "Onsite")
        assert accept is True
        assert mode == "onsite"

    def test_mumbai_accepted(self):
        accept, mode, _ = qf.location_decision("Mumbai", "Onsite")
        assert accept is True
        assert mode == "onsite"

    def test_gurgaon_accepted(self):
        accept, mode, _ = qf.location_decision("Gurgaon", "Onsite")
        assert accept is True

    def test_noida_accepted(self):
        accept, mode, _ = qf.location_decision("Noida", "Onsite")
        assert accept is True

    def test_delhi_accepted(self):
        accept, mode, _ = qf.location_decision("New Delhi", "Onsite")
        assert accept is True

    def test_pune_accepted(self):
        accept, mode, _ = qf.location_decision("Pune", "Onsite")
        assert accept is True

    def test_hyderabad_accepted(self):
        accept, mode, _ = qf.location_decision("Hyderabad", "Onsite")
        assert accept is True

    def test_chennai_accepted(self):
        accept, mode, _ = qf.location_decision("Chennai", "Onsite")
        assert accept is True

    def test_jaipur_accepted(self):
        accept, mode, _ = qf.location_decision("Jaipur", "Onsite")
        assert accept is True

    def test_ahmedabad_accepted(self):
        accept, mode, _ = qf.location_decision("Ahmedabad", "Onsite")
        assert accept is True

    def test_kolkata_accepted(self):
        accept, mode, _ = qf.location_decision("Kolkata", "Onsite")
        assert accept is True

    def test_indore_accepted(self):
        accept, mode, _ = qf.location_decision("Indore", "Onsite")
        assert accept is True


class TestLocationDecisionAllIndiaCities:
    def test_lucknow_accepted(self):
        accept, mode, _ = qf.location_decision("Lucknow", "Onsite")
        assert accept is True
        assert mode == "onsite"

    def test_coimbatore_accepted(self):
        accept, mode, _ = qf.location_decision("Coimbatore", "Onsite")
        assert accept is True

    def test_ranchi_accepted(self):
        accept, mode, _ = qf.location_decision("Ranchi", "Onsite")
        assert accept is True
        assert mode == "onsite"

    def test_unrecognized_location_rejected(self):
        # No known Indian city, no remote signal, no India context → can't confirm.
        accept, mode, _ = qf.location_decision("Xyzabad", "Onsite")
        assert accept is False
        assert mode == "other"


class TestLocationDecisionRemote:
    def test_remote_india_eligible_accepted(self):
        accept, mode, _ = qf.location_decision("Remote", "Remote", "Open to candidates across India")
        assert accept is True
        assert mode == "remote"

    def test_remote_foreign_only_rejected(self):
        accept, mode, _ = qf.location_decision("Remote", "Remote", "US only, no sponsorship")
        assert accept is False
        assert mode == "remote"

    def test_body_text_fallback_accepted_city(self):
        accept, mode, _ = qf.location_decision("", "", "This role is based in Pune, onsite only.")
        assert accept is True
        assert mode == "onsite"

    def test_body_text_fallback_remote(self):
        accept, mode, _ = qf.location_decision("", "", "This is a fully remote role open to India.")
        assert accept is True
        assert mode == "remote"

    def test_empty_unknown_rejected(self):
        accept, mode, _ = qf.location_decision("", "", "Great opportunity, apply now!")
        assert accept is False
        assert mode == "other"

    def test_foreign_city_not_rescued_by_body_remote_mention(self):
        # Structured "onsite in a foreign city" must win even if the body text
        # happens to mention "remote" elsewhere (e.g. "hybrid, remote-friendly team").
        accept, mode, _ = qf.location_decision("New York", "Onsite", "Great remote-friendly culture")
        assert accept is False


class TestEvaluatePostScoring:
    def test_accepted_onsite_city_gets_score_bonus(self):
        analysis = {
            "roles": ["Software Development Intern"],
            "location": "Pune",
            "type": "Onsite",
            "stipend": "₹15,000/month",
            "apply_link": "https://careers.acme.com/apply/123",
            "company": "Acme",
        }
        post = {"text": "Hiring a Software Development Intern in Pune. Apply at https://careers.acme.com/apply/123"}
        result = qf.evaluate_post(analysis, post)
        assert result["accept"] is True
        assert result["resolved_mode"] == "onsite"

    def test_foreign_city_rejected(self):
        analysis = {
            "roles": ["Software Development Intern"],
            "location": "New York",
            "type": "Onsite",
            "stipend": "₹15,000/month",
            "apply_link": "https://careers.acme.com/apply/123",
            "company": "Acme",
        }
        post = {"text": "Hiring in New York"}
        result = qf.evaluate_post(analysis, post)
        assert result["accept"] is False
