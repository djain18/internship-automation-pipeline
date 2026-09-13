"""A site-scraped or Hunter-found contact often has no name (kind
"site_published_role_mailbox", or a bare Hunter pick with no first/last
name) -- the internship section used to print `contact.name or
contact.status`, which rendered "available" with the actual email nowhere
in the digest. These tests are the direct regression check for that fix.
"""

from digest import _section


def _record(**contact_overrides):
    return {
        "company": "Acme",
        "title": "Founder's Office Intern",
        "score": 90,
        "llm_fit_score": 88,
        "llm_rank": 1,
        "llm_rank_reason": "strong fit",
        "lane": "ai",
        "location": "Bengaluru",
        "location_class": "onsite",
        "posted_date": "2026-09-10",
        "posted_date_basis": "observed",
        "verification_status": "published_by_source",
        "source_confidence": "high",
        "source_url": "https://acme.com/careers",
        "resume": "Daksh-Jain-founders_office",
        "selected_contact": contact_overrides,
    }


def test_nameless_email_contact_is_actually_shown() -> None:
    """The exact failure mode: name="" status="available" used to hide the
    email entirely, printing just "- Contact: available"."""
    rendered = _section("Test", [_record(
        status="available",
        email="careers@acme.com",
        source_url="https://acme.com/careers",
        contact_priority="fallback_generic",
    )])
    assert "careers@acme.com" in rendered
    assert "- Contact email: careers@acme.com" in rendered
    assert "- Contact source: https://acme.com/careers" in rendered
    assert "- Contact priority: fallback_generic" in rendered


def test_named_contact_still_shows_name_first() -> None:
    rendered = _section("Test", [_record(
        status="available",
        name="Aarav",
        email="aarav@acme.com",
        source_url="https://acme.com/team",
        contact_priority="preferred_named",
    )])
    assert "- Contact: Aarav" in rendered
    assert "- Contact email: aarav@acme.com" in rendered


def test_research_required_contact_shows_no_email_lines() -> None:
    rendered = _section("Test", [_record(
        status="contact_research_required",
        source_url="https://acme.com",
    )])
    assert "- Contact: contact_research_required" in rendered
    assert "Contact email:" not in rendered
    assert "Contact priority:" not in rendered
