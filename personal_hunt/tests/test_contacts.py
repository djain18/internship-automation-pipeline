from contacts import choose_contact


def test_named_published_contact_beats_generic_fallback() -> None:
    contact = choose_contact({
        "company_url": "https://example.com",
        "research": {"published_emails": ["careers@example.com", "aarav@example.com"]},
    })
    assert contact["email"] == "aarav@example.com"
    assert contact["contact_priority"] == "preferred_named"


def test_verified_generic_careers_mailbox_is_visible_fallback() -> None:
    contact = choose_contact({
        "company_url": "https://example.com",
        "research": {"published_emails": ["careers@example.com"]},
    })
    assert contact["email"] == "careers@example.com"
    assert contact["contact_priority"] == "fallback_generic"


def test_support_and_press_mailboxes_are_excluded() -> None:
    contact = choose_contact({
        "company_url": "https://example.com",
        "research": {"published_emails": ["support@example.com", "press@example.com"]},
    })
    assert contact["status"] == "contact_research_required"
    assert "email" not in contact


def test_unverified_generic_record_email_is_not_exposed() -> None:
    contact = choose_contact({
        "source_url": "https://example.com/job",
        "contact": {"email": "careers@example.com", "verification_status": "unverified"},
    })
    assert contact["email"] == ""
    assert contact["contact_priority"] == "unverified_lead"
