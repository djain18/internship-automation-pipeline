from contacts import attach_contact, choose_contact


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


def test_linkedin_url_from_research_published_urls() -> None:
    """LinkedIn URL from company site research is captured."""
    contact = choose_contact({
        "source_url": "https://example.com/job",
        "contact": {"name": "Aarav", "email": "aarav@example.com", "verification_status": "published_by_source"},
        "research": {"published_linkedin_urls": ["https://www.linkedin.com/in/aarav-sharma"]},
    })
    assert contact["linkedin"] == "https://www.linkedin.com/in/aarav-sharma"


def test_linkedin_url_from_deep_problem_research() -> None:
    """LinkedIn URL from problem research is captured."""
    contact = choose_contact({
        "source_url": "https://example.com/job",
        "contact": {"name": "Aarav", "email": "aarav@example.com"},
        "deep_problem_research": {"published_linkedin_urls": ["https://linkedin.com/in/aarav"]},
    })
    assert contact["linkedin"] == "https://linkedin.com/in/aarav"


def test_site_email_from_deep_problem_research() -> None:
    """A discovered/watchlist company's scraped emails live in
    deep_problem_research, not research -- reading only the latter silently
    dropped every one of them (problem_research.py used to discard the
    scraped list entirely before this fix)."""
    contact = choose_contact({
        "source_url": "https://example.com/company",
        "deep_problem_research": {"published_emails": ["founders@example.com"]},
    })
    assert contact["email"] == "founders@example.com"
    assert contact["basis"] == "site_published_role_mailbox"


def test_site_email_prefers_research_over_deep_research_when_both_present() -> None:
    contact = choose_contact({
        "source_url": "https://example.com/company",
        "research": {"published_emails": ["jane@example.com"]},
        "deep_problem_research": {"published_emails": ["founders@example.com"]},
    })
    assert contact["email"] == "jane@example.com"


def test_linkedin_url_never_constructed_from_name() -> None:
    """LinkedIn URL is never guessed or constructed from name."""
    contact = choose_contact({
        "source_url": "https://example.com/job",
        "company": "Example Inc",
        "contact": {"name": "Aarav Sharma", "email": "aarav@example.com"},
        "research": {},
    })
    # No LinkedIn URL should be present unless explicitly provided
    assert contact["linkedin"] == ""


def test_role_priority_founder_preferred() -> None:
    """Founder role is prioritized highest."""
    from contacts import _role_priority
    assert _role_priority("Founder") < _role_priority("Chief of Staff")
    assert _role_priority("Co-Founder") < _role_priority("Head of Ops")
    assert _role_priority("Head of Ops") < _role_priority("Named Contact")


def test_role_priority_in_contact_choice() -> None:
    """Founder contacts get preferred priority."""
    contact_founder = choose_contact({
        "source_url": "https://example.com/job",
        "contact": {"name": "Aarav", "email": "aarav@example.com", "role": "Founder", "verification_status": "published_by_source"},
    })
    assert contact_founder["contact_priority"] == "preferred_named_senior"
    assert "Founder" in contact_founder["role"]
    generic = choose_contact({
        "source_url": "https://example.com/job",
        "contact": {"name": "Aarav", "email": "aarav@example.com", "role": "Recruiter", "verification_status": "published_by_source"},
    })
    assert generic["contact_priority"] == "preferred_named"


def test_site_linkedin_url_is_not_attached_to_a_different_person() -> None:
    """Team-page profiles belong to whoever they name, not to the contact."""
    contact = choose_contact({
        "source_url": "https://example.com/job",
        "contact": {"name": "Aarav Sharma", "email": "aarav@example.com"},
        "research": {"published_linkedin_urls": [
            "https://www.linkedin.com/in/priya-nair",
            "https://www.linkedin.com/in/aarav-sharma",
        ]},
    })
    assert contact["linkedin"] == "https://www.linkedin.com/in/aarav-sharma"


def test_site_linkedin_url_alone_never_manufactures_a_contact() -> None:
    """No name, no email: a scraped profile must not become "available"."""
    contact = choose_contact({
        "source_url": "https://example.com/job",
        "research": {"published_linkedin_urls": ["https://www.linkedin.com/in/priya-nair"]},
    })
    assert contact["status"] == "contact_research_required"


def test_attach_contact_skips_hunter_when_choose_contact_already_found_one() -> None:
    """The single wrapping point for all three call sites: Hunter must never
    fire when a real contact was already found -- it exists to fill gaps,
    not to override or re-verify what the record itself already carries."""
    record = {
        "source_url": "https://example.com/job",
        "contact": {"name": "Aarav", "email": "aarav@example.com", "verification_status": "published_by_source"},
    }
    hunter_ctx = {"scoring": {}, "state": None, "month": "2026-09"}
    result = attach_contact(record, hunter_ctx)
    assert result["email"] == "aarav@example.com"
    # No status was recorded, because Hunter was never called.
    assert hunter_ctx.get("statuses", []) == []


def test_attach_contact_falls_back_to_hunter_and_records_status(monkeypatch) -> None:
    record = {"source_url": "https://example.com/job", "company_url": "https://example.com"}
    hunter_ctx = {"scoring": {}, "state": None, "month": "2026-09"}

    def fake_lookup(_record, _scoring, _state, _month):
        return {"status": "available", "email": "founder@example.com"}, "ok"

    monkeypatch.setattr("hunter.find_company_contact_with_status", fake_lookup)
    result = attach_contact(record, hunter_ctx)
    assert result["email"] == "founder@example.com"
    assert hunter_ctx["statuses"] == ["ok"]


def test_attach_contact_keeps_research_required_when_hunter_finds_nothing(monkeypatch) -> None:
    record = {"source_url": "https://example.com/job", "company_url": "https://example.com"}
    hunter_ctx = {"scoring": {}, "state": None, "month": "2026-09"}

    monkeypatch.setattr(
        "hunter.find_company_contact_with_status",
        lambda *_a, **_k: (None, "no_match"),
    )
    result = attach_contact(record, hunter_ctx)
    assert result["status"] == "contact_research_required"
    assert hunter_ctx["statuses"] == ["no_match"]
