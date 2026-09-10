"""Tests for execution/role_taxonomy.py — the shared role taxonomy and the
nightly per-role balance.

Context: the live sheet was 72% Marketing with zero Founder's Office / AI
Automation / Forward Deployed rows, because (a) no query existed for those
roles and (b) nothing capped how many of one field could publish. These tests
pin both halves of the fix.
"""

import pytest

import role_taxonomy as rt


class TestInferTrack:
    """Ordering is the whole game: specific 2026 role families must resolve
    before the broad buckets that would otherwise swallow them."""

    @pytest.mark.parametrize("title,track", [
        ("AI Automation Intern", "ai_automation"),
        ("AI Agent Engineering Intern", "ai_automation"),
        ("GenAI Prompt Engineer Intern", "ai_automation"),
        ("Product Engineer Intern", "product_engineering"),
        ("Founding Engineer Intern", "product_engineering"),
        ("Forward Deployed Engineer Intern", "forward_deployed"),
        ("Solutions Engineer Intern", "forward_deployed"),
        ("Founder's Office Intern", "founders_office"),
        ("Chief of Staff Intern", "founders_office"),
        ("Backend Developer Intern", "software"),
        ("Data Science Intern", "data_ml"),
        ("Product Management Intern", "product"),
        ("UI/UX Design Intern", "design"),
        ("Business Operations Intern", "business_ops"),
        ("Business Development Intern", "sales_bd"),
        ("Digital Marketing Intern", "marketing_content"),
        ("Content Writer Intern", "marketing_content"),
        ("Finance Intern", "finance_hr_legal"),
        ("Talent Acquisition Intern", "finance_hr_legal"),
    ])
    def test_classifies(self, title, track):
        assert rt.infer_track(title) == track

    def test_ai_automation_beats_data(self):
        # "AI Automation Engineer" contains no data keywords, but a bare "ai"
        # match in the Data/AI rule would have caught it if ordered first.
        assert rt.infer_track("AI Automation Engineer") == "ai_automation"

    def test_product_engineer_is_not_software(self):
        assert rt.infer_track("Product Engineer") == "product_engineering"
        assert rt.infer_track("Software Engineer") == "software"

    def test_marketing_beats_design_on_video_tag(self):
        # Regression carried over from _infer_cluster: a marketing intern
        # tagged "Video Editing" was landing in Design.
        assert rt.infer_cluster("Digital Marketing Intern", ["Video Editing"]) == "Marketing"

    @pytest.mark.parametrize("title", ["Fundraising Intern", "Training Coordinator Intern"])
    def test_ai_needs_word_boundary(self, title):
        # "ai" inside fundraising / training must not match the Data/AI rule.
        assert rt.infer_track(title) != "data_ml"

    @pytest.mark.parametrize("title", ["Talent Acquisition Intern", "Equity Research Intern"])
    def test_ui_needs_word_boundary(self, title):
        # "ui" inside acquisition / equity must not match Design.
        assert rt.infer_track(title) != "design"

    def test_unknown_falls_back(self):
        assert rt.infer_track("") == "business_ops"
        assert rt.infer_cluster("") == "Operations"

    def test_tags_are_considered(self):
        assert rt.infer_track("Intern", ["Machine Learning", "Python"]) == "data_ml"

    def test_track_is_always_known(self):
        for title in ["", "Intern", "Widget Wrangler", "Signal Processing Engineer"]:
            assert rt.infer_track(title) in rt.TRACK_KEYS


class TestClusterCompatibility:
    """The site's filter chips and subscribers' saved Firestore `roles` are
    these exact strings. Renaming one silently breaks saved preferences."""

    LEGACY_LABELS = {
        "Founder's Office", "Forward Deployed", "AI Automation", "Software",
        "Data/AI", "Product", "Design", "Marketing", "Finance", "Business Dev",
        "HR", "Content", "Legal", "Operations",
    }

    def test_every_legacy_label_still_emitted(self):
        assert self.LEGACY_LABELS <= set(rt.CLUSTER_LABELS)

    def test_cluster_maps_back_to_its_track(self):
        for label in rt.CLUSTER_LABELS:
            assert rt.track_for_cluster(label) in rt.TRACK_KEYS

    def test_marketing_and_content_share_a_track(self):
        # Separate chips on the site, one quota bucket — otherwise a "3
        # marketing + 3 content" digest reads as six marketing roles.
        assert rt.track_for_cluster("Marketing") == rt.track_for_cluster("Content")

    def test_finance_hr_legal_share_a_track(self):
        assert (rt.track_for_cluster("Finance")
                == rt.track_for_cluster("HR")
                == rt.track_for_cluster("Legal"))


class TestQueryPlan:
    def test_covers_every_track(self):
        tracks = {q["track"] for q in rt.query_plan()}
        assert tracks == set(rt.TRACK_KEYS)

    def test_scarce_flag_matches_track(self):
        for q in rt.query_plan():
            assert q["scarce"] == (q["track"] in rt.SCARCE_TRACKS)

    def test_every_track_gets_a_remote_pass(self):
        remote = {q["track"] for q in rt.query_plan()
                  if q["query"].endswith(rt.REMOTE_SUFFIX)}
        assert remote == set(rt.TRACK_KEYS)

    def test_scarce_roles_are_actually_searched_for(self):
        # The original bug: no query mentioned these at all.
        blob = " ".join(q["query"] for q in rt.query_plan())
        for term in ("founders office", "forward deployed", "ai automation",
                     "product engineer", "business operations"):
            assert term in blob

    def test_marketing_no_longer_dominates_the_plan(self):
        plan = rt.query_plan()
        marketing = sum(1 for q in plan if q["track"] == "marketing_content")
        assert marketing < sum(1 for q in plan if q["track"] == "ai_automation")

    def test_rotation_shifts_wide_cities_but_not_size(self):
        a, b = rt.query_plan(0), rt.query_plan(3)
        assert len(a) == len(b)
        assert [q["query"] for q in a] != [q["query"] for q in b]

    def test_rotation_covers_every_city_across_a_week(self):
        seen = set()
        for day in range(7):
            for q in rt.query_plan(day):
                for city in rt.ALL_CITIES:
                    if q["query"].endswith(city):
                        seen.add(city)
        assert seen == set(rt.ALL_CITIES)


def _post(title, score=50, tags=None):
    return {"title": title, "tags": tags or [], "quality_score": score}


class TestBalance:
    def test_empty_in_empty_out(self):
        assert rt.balance([]) == []

    def test_caps_a_flooded_track(self):
        posts = [_post("Digital Marketing Intern", 50 + i) for i in range(26)]
        posts += [_post("Backend Engineer Intern", 60) for _ in range(3)]
        out = rt.balance(posts)
        mix = rt.mix(out)
        assert mix["Software"] == 3
        # Fair share is 5; the ceiling caps redistribution at 2x.
        assert mix["Marketing"] == rt.DEFAULT_MAX_PER_TRACK

    def test_never_pads(self):
        posts = [_post("Backend Engineer Intern")]
        assert len(rt.balance(posts, total_target=45)) == 1

    def test_keeps_highest_scoring_within_a_track(self):
        posts = [_post("Digital Marketing Intern", score=i) for i in range(20)]
        out = rt.balance(posts, quota=3, max_per_track=3)
        assert sorted(p["quality_score"] for p in out) == [17, 18, 19]

    def test_healthy_night_is_evenly_spread(self):
        posts = []
        for title in ["AI Automation Intern", "Founders Office Intern",
                      "Backend Engineer Intern", "Product Design Intern",
                      "Digital Marketing Intern", "Business Operations Intern",
                      "Data Science Intern"]:
            posts += [_post(title) for _ in range(8)]
        mix = rt.mix(rt.balance(posts))
        assert max(mix.values()) - min(mix.values()) <= 2

    def test_redistribution_fills_from_tracks_with_supply(self):
        # One dry track's slots must not be wasted.
        posts = [_post("Backend Engineer Intern", 50 + i) for i in range(12)]
        out = rt.balance(posts, quota=5, total_target=45)
        assert len(out) == rt.DEFAULT_MAX_PER_TRACK  # 5 fair + 5 redistributed

    def test_does_not_mutate_input(self):
        posts = [_post("Digital Marketing Intern") for _ in range(20)]
        before = len(posts)
        rt.balance(posts)
        assert len(posts) == before

    def test_handles_missing_and_bad_scores(self):
        posts = [{"title": "Backend Engineer Intern"},
                 {"title": "Backend Engineer Intern", "quality_score": None},
                 {"title": "Backend Engineer Intern", "quality_score": "high"}]
        assert len(rt.balance(posts)) == 3

    def test_falls_back_to_role_key(self):
        # clean_post carries both "title" and "role"; older records only "role".
        out = rt.balance([{"role": "AI Automation Intern", "quality_score": 90}])
        assert rt.mix(out) == {"AI Automation": 1}
