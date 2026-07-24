"""Unit tests for send_daily_digest.py's subscriber-matching logic, updated
for Firestore's native-list field shape (roles/cities are real lists, not
Resend's comma-joined strings)."""

import send_daily_digest as digest


class TestPrefs:
    def test_list_shaped_roles_and_cities(self):
        contact = {"roles": ["Software", "Data/AI"], "cities": ["Bangalore"]}
        roles, cities = digest._prefs(contact)
        assert roles == ["software", "data/ai"]
        assert cities == ["bangalore"]

    def test_missing_fields_default_empty(self):
        roles, cities = digest._prefs({})
        assert roles == []
        assert cities == []

    def test_non_list_fields_do_not_crash(self):
        # A malformed doc (e.g. written by a buggy client before the
        # Firestore rule validation existed) must not crash matching.
        roles, cities = digest._prefs({"roles": "not-a-list", "cities": None})
        assert roles == []
        assert cities == []


class TestMatchFor:
    def _listings(self):
        return [
            {"cluster": "Software", "title": "Backend Intern", "location": "Bangalore", "hoursAgo": 2},
            {"cluster": "Marketing", "title": "SEO Intern", "location": "Mumbai", "hoursAgo": 5},
        ]

    def test_matches_by_role_and_city(self):
        contact = {"roles": ["Software"], "cities": ["Bangalore"]}
        picks = digest.match_for(contact, self._listings())
        assert len(picks) == 1
        assert picks[0]["title"] == "Backend Intern"

    def test_no_prefs_returns_freshest(self):
        picks = digest.match_for({}, self._listings())
        assert len(picks) == 2

    def test_malformed_doc_falls_back_to_freshest_not_crash(self):
        contact = {"roles": "not-a-list", "cities": 12345}
        picks = digest.match_for(contact, self._listings())
        assert len(picks) == 2
