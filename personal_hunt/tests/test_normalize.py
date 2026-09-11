from config import load_all
from normalize import classify_location, normalize_record


def test_location_priority_classes() -> None:
    assert classify_location("Bangalore - onsite") == ("bengaluru_onsite", "onsite")
    assert classify_location("Bengaluru hybrid") == ("bengaluru_hybrid", "hybrid")
    assert classify_location("Remote - India") == ("india_remote", "remote")
    assert classify_location("Mumbai onsite") == ("other", "unknown")


def test_hard_excludes_oversized_company() -> None:
    config = load_all()
    record = normalize_record(
        {
            "source": "yc_bengaluru",
            "source_url": "https://example.com/role",
            "company": "HugeCo",
            "title": "Founder’s Office Intern",
            "description": "Work with founders across growth and operations.",
            "location": "Bengaluru onsite",
            "employee_count": 401,
        },
        config["roles"],
        config["scoring"],
        "2026-09-08",
    )
    assert not record["eligible"]
    assert "company_above_400_employees" in record["rejection_reasons"]


def test_specialist_role_is_rejected() -> None:
    config = load_all()
    record = normalize_record(
        {
            "source": "yc_bengaluru",
            "source_url": "https://example.com/engineer",
            "company": "CodeCo",
            "title": "Software Engineer Intern",
            "description": "Write backend code.",
            "location": "Bengaluru onsite",
        },
        config["roles"],
        config["scoring"],
        "2026-09-08",
    )
    assert "specialist_only_role" in record["rejection_reasons"]


def test_unverified_linkedin_and_bad_duration_are_rejected() -> None:
    config = load_all()
    record = normalize_record(
        {
            "source": "linkedin_public_post",
            "source_url": "https://www.linkedin.com/posts/example",
            "company": "SmallCo",
            "title": "Founder’s Office Intern",
            "description": "Work with founders across growth and operations.",
            "location": "Bengaluru onsite",
            "duration": "1 months",
            "verification_status": "machine_collected",
        },
        config["roles"],
        config["scoring"],
        "2026-09-08",
    )
    assert "linkedin_post_requires_manual_verification" in record["rejection_reasons"]
    assert "duration_outside_target_window" in record["rejection_reasons"]


def test_posting_recency_accepts_ten_days_and_rejects_eleven() -> None:
    config = load_all()
    base = {
        "source": "yc_bengaluru",
        "source_url": "https://example.com/founders-office",
        "company": "FreshCo",
        "title": "Founder’s Office Intern",
        "description": "Work with founders across growth and operations.",
        "location": "Bengaluru onsite",
    }
    ten = normalize_record(
        {**base, "posted_at": "2026-08-30T00:00:00Z"},
        config["roles"],
        config["scoring"],
        "2026-09-09",
    )
    eleven = normalize_record(
        {**base, "posted_at": "2026-08-29T00:00:00Z"},
        config["roles"],
        config["scoring"],
        "2026-09-09",
    )
    assert "posted_over_10_days" not in ten["rejection_reasons"]
    assert "posted_over_10_days" in eleven["rejection_reasons"]


def test_approved_linkedin_actor_is_low_unverified_but_not_source_rejected() -> None:
    config = load_all()
    record = normalize_record(
        {
            "source": "linkedin_posts_apify",
            "source_url": "https://www.linkedin.com/posts/example",
            "company": "SmallCo",
            "title": "Founder’s Office Intern",
            "description": "Work with founders across growth and operations.",
            "location": "Bengaluru onsite",
        },
        config["roles"],
        config["scoring"],
        "2026-09-09",
    )
    assert record["source_confidence"] == "low"
    assert record["verification_status"] == "machine_collected_unverified"
    assert "linkedin_post_requires_manual_verification" not in record["rejection_reasons"]


def test_lnkd_redirect_from_other_adapter_is_gated() -> None:
    config = load_all()
    record = normalize_record(
        {
            "source": "ftb_internships",
            "source_url": "https://lnkd.in/example",
            "company": "RedirectCo",
            "title": "Founder’s Office Intern",
            "description": "Work with founders across growth and operations.",
            "location": "Bengaluru onsite",
        },
        config["roles"],
        config["scoring"],
        "2026-09-09",
    )
    assert "linkedin_post_requires_manual_verification" in record["rejection_reasons"]



def _record(**overrides: object) -> dict:
    config = load_all()
    payload = {
        "source": "yc_bengaluru",
        "source_url": "https://example.com/role",
        "company": "SeedCo",
        "title": "Operations Intern",
        "description": "Support the team.",
        "location": "Bengaluru onsite",
    }
    payload.update(overrides)
    return normalize_record(payload, config["roles"], config["scoring"], "2026-09-08")


def test_broad_title_requires_two_function_or_leadership_evidence() -> None:
    thin = _record(title="Business Development Intern")
    assert "role_not_cross_functional" in thin["rejection_reasons"]

    record = _record(
        title="Business Development Intern",
        description="Support partnerships, customer onboarding, and market research.",
    )
    assert record["eligible"], record["rejection_reasons"]


def test_tier_one_role_family_is_not_matched_from_the_description() -> None:
    """A description mentioning growth must not admit an unrelated role."""
    record = _record(
        title="Marketing Intern",
        description="Help our growth and operations team with campaign assets.",
    )
    assert "role_not_cross_functional" in record["rejection_reasons"]


def test_anywhere_headquarters_passes_with_bangalore_posting() -> None:
    """HQ city is never a filter; only the internship location matters."""
    record = _record(
        company="GlobalCorp",
        title="Founder's Office Intern",
        description="Work with founders across growth and operations.",
        location="Bangalore onsite",
    )
    assert "location_out_of_scope" not in record["rejection_reasons"]
    assert record["eligible"], record["rejection_reasons"]


def test_ceo_office_title_is_accepted() -> None:
    record = _record(title="CEO's Office Intern")
    assert record["eligible"], record["rejection_reasons"]


def test_right_hand_and_end_to_end_signal_cross_functional_scope() -> None:
    record = _record(
        title="Marketing Intern",
        description="Work as the right-hand to the founder across launches.",
    )
    assert record["eligible"], record["rejection_reasons"]
    record = _record(
        title="Operations Intern",
        description="Own merchant onboarding end-to-end with Excel tracking.",
    )
    assert record["eligible"], record["rejection_reasons"]


def test_fundraising_and_analytics_count_as_distinct_functions() -> None:
    record = _record(
        title="Operations Intern",
        description="Build Excel dashboards and support investor updates.",
    )
    assert record["eligible"], record["rejection_reasons"]


def test_internship_signal_may_come_from_the_description() -> None:
    record = _record(title="Growth Associate", description="A 6 month internship.")
    assert "not_internship_or_fellowship" not in record["rejection_reasons"]


def test_internal_and_international_do_not_count_as_internship_signals() -> None:
    record = _record(
        title="Operations Manager",
        description=(
            "Own internal reporting for our international teams across the internet."
        ),
    )
    assert "not_internship_or_fellowship" in record["rejection_reasons"]


def test_incidental_intern_mentions_do_not_make_a_full_time_role_an_internship() -> None:
    """Real full-time postings that merely say the word, seen in the 2026-09-10 run."""
    for description in (
        "Onboarding with your fellow new colleagues.",
        "Minimum 3+ years of post-internship, full-time professional experience.",
        "Learn from seniors and gradually help junior teammates or interns.",
    ):
        record = _record(title="Backend Engineer", description=description)
        assert "not_internship_or_fellowship" in record["rejection_reasons"], description


def test_role_shaped_intern_phrase_rescues_a_misspelled_title() -> None:
    """The 2026-09-10 run contained a real posting titled "Product Inern"."""
    record = _record(
        title="Product Inern",
        description="The Economic Times seeks a proactive Product Operations Intern.",
    )
    assert "not_internship_or_fellowship" not in record["rejection_reasons"]


def test_duration_window_comes_from_scoring_config() -> None:
    assert "duration_outside_target_window" not in _record(
        title="Operations Intern", duration_months=9
    )["rejection_reasons"]
    assert "duration_outside_target_window" in _record(
        title="Operations Intern", duration_months=18
    )["rejection_reasons"]



def test_title_family_match_scores_as_an_explicit_role_match() -> None:
    """A role family admitted by `accepted_title` must also earn role_breadth.

    Without this the record clears hard_exclusions and is then killed by
    below_publish_threshold, which is how the 2026-09-10 live dry run lost three
    genuine Bengaluru internships.
    """
    from datetime import date

    from score import score_record

    config = load_all()
    record = _record(
        title="Business Development Intern",
        description="Support partnerships, customer onboarding, and market research.",
        location="Bengaluru onsite",
    )
    assert record["eligible"], record["rejection_reasons"]
    scored = score_record(
        dict(record), config["roles"], config["scoring"], date(2026, 9, 8)
    )
    assert scored["score_components"]["role_breadth"] == (
        config["scoring"]["weights"]["role_breadth"]
    )
    assert "role:title_family_match" in scored["score_reasons"]
