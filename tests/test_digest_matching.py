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

    def test_no_cap_on_exact_matches(self):
        listings = [
            {"cluster": "Software", "title": f"Backend Intern {i}", "location": "Bangalore", "hoursAgo": i}
            for i in range(12)
        ]
        contact = {"roles": ["Software"], "cities": ["Bangalore"]}
        picks = digest.match_for(contact, listings)
        assert len(picks) == 12

    def test_falls_back_to_role_only_when_no_city_match(self):
        # Role matches in a different city than requested — no exact
        # role+city hit, so relax city before giving up on role entirely.
        contact = {"roles": ["Software"], "cities": ["Hyderabad"]}
        picks = digest.match_for(contact, self._listings())
        assert len(picks) == 1
        assert picks[0]["title"] == "Backend Intern"

    def test_falls_back_to_city_only_when_no_role_match(self):
        # City matches but the requested field doesn't exist in that city —
        # relax role before giving up on city entirely.
        contact = {"roles": ["Design"], "cities": ["Bangalore"]}
        picks = digest.match_for(contact, self._listings())
        assert len(picks) == 1
        assert picks[0]["title"] == "Backend Intern"

    def test_falls_back_to_freshest_when_nothing_relates(self):
        contact = {"roles": ["Design"], "cities": ["Hyderabad"]}
        picks = digest.match_for(contact, self._listings())
        assert len(picks) == 2


class TestExcludeSent:
    """Regression coverage for the "same internships two days in a row" bug:
    a subscriber must not be re-sent a listing id already recorded as sent."""

    def _candidates(self):
        return [
            {"id": "sh-aaa", "title": "Backend Intern"},
            {"id": "sh-bbb", "title": "SEO Intern"},
        ]

    def test_drops_previously_sent_ids(self):
        picks = digest._exclude_sent(self._candidates(), ["sh-aaa"])
        assert [p["id"] for p in picks] == ["sh-bbb"]

    def test_no_history_returns_all(self):
        picks = digest._exclude_sent(self._candidates(), [])
        assert len(picks) == 2

    def test_everything_already_sent_returns_empty(self):
        picks = digest._exclude_sent(self._candidates(), ["sh-aaa", "sh-bbb"])
        assert picks == []


class TestMarkSent:
    class _FakeDocRef:
        def __init__(self, store, uid):
            self._store = store
            self._uid = uid

        def update(self, data):
            self._store[self._uid] = data

    class _FakeCollection:
        def __init__(self, store):
            self._store = store

        def document(self, uid):
            return TestMarkSent._FakeDocRef(self._store, uid)

    class _FakeDb:
        def __init__(self):
            self.store = {}

        def collection(self, name):
            return TestMarkSent._FakeCollection(self.store)

    def test_merges_new_ids_with_history(self):
        db = self._FakeDb()
        digest.mark_sent(db, "uid1", ["sh-bbb"], ["sh-aaa"])
        assert db.store["uid1"]["sent_listing_ids"] == ["sh-aaa", "sh-bbb"]

    def test_does_not_duplicate_ids(self):
        db = self._FakeDb()
        digest.mark_sent(db, "uid1", ["sh-aaa"], ["sh-aaa"])
        assert db.store["uid1"]["sent_listing_ids"] == ["sh-aaa"]

    def test_caps_history_length(self):
        db = self._FakeDb()
        history = [f"sh-{i}" for i in range(digest.SENT_HISTORY_CAP)]
        digest.mark_sent(db, "uid1", ["sh-new"], history)
        result = db.store["uid1"]["sent_listing_ids"]
        assert len(result) == digest.SENT_HISTORY_CAP
        assert result[-1] == "sh-new"
        assert result[0] == "sh-1"  # oldest entry dropped to make room

    def test_no_db_is_a_noop(self):
        # Must not raise when Firestore isn't configured (local dry run).
        digest.mark_sent(None, "uid1", ["sh-aaa"], [])


def _listing(idx, cluster, hours=1):
    return {"id": f"sh-{idx}", "title": f"{cluster} Intern", "org": "Acme",
            "cluster": cluster, "location": "Bangalore", "hoursAgo": hours}


class TestDiversify:
    """The all-marketing digest this guards against: the sheet was 72%
    Marketing, and match_for sorts by freshness with no role awareness, so the
    email mirrored the skew exactly."""

    def test_empty_in_empty_out(self):
        assert digest.diversify([]) == []

    def test_caps_a_single_role(self):
        listings = [_listing(i, "Marketing") for i in range(20)]
        out = digest.diversify(listings)
        assert len(out) == digest.DIGEST_MAX_PER_ROLE

    def test_marketing_and_content_share_the_cap(self):
        # Two chips on the site, one role to the reader.
        listings = ([_listing(i, "Marketing") for i in range(5)]
                    + [_listing(10 + i, "Content") for i in range(5)])
        assert len(digest.diversify(listings)) == digest.DIGEST_MAX_PER_ROLE

    def test_interleaves_so_the_top_rows_differ(self):
        listings = ([_listing(i, "Marketing") for i in range(5)]
                    + [_listing(10 + i, "Software") for i in range(5)]
                    + [_listing(20 + i, "AI Automation") for i in range(5)])
        top = [l["cluster"] for l in digest.diversify(listings)[:3]]
        assert len(set(top)) == 3

    def test_preserves_freshness_order_within_a_role(self):
        listings = [_listing(1, "Software", hours=1),
                    _listing(2, "Software", hours=5),
                    _listing(3, "Software", hours=9)]
        assert [l["id"] for l in digest.diversify(listings)] == ["sh-1", "sh-2", "sh-3"]

    def test_keeps_everything_when_already_balanced(self):
        listings = [_listing(i, c) for i, c in
                    enumerate(["Software", "Design", "Marketing", "Data/AI"])]
        assert len(digest.diversify(listings)) == 4

    def test_missing_cluster_does_not_crash(self):
        assert len(digest.diversify([{"id": "sh-1", "hoursAgo": 1}])) == 1
