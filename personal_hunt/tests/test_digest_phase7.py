"""Tests for Phase 7: Email restructure with watchlist movement and problem briefs.

These tests verify:
1. Watchlist movement section renders correctly
2. Problem briefs section includes all expected fields
3. Fenced prompt blocks handle missing evidence honestly
4. Blocked outreach drafts show why they're blocked
5. Integration: real pipeline output → render_digest → content is present
"""

from datetime import date
from pathlib import Path

from config import AUTOMATION_ROOT, load_all
from digest import (
    render_digest,
    render_html_digest,
    _watchlist_movement_section,
    _problem_briefs_section,
    _problem_brief_block,
)
from fetch_sources import fixture_health, load_json_records
from pipeline import run_pipeline


def test_watchlist_movement_section_shows_activity_summary():
    """Watchlist movement section displays one-line status per watchlist company."""
    discovered = [
        {
            "company": "Emergent",
            "company_url_basis": "watchlist",
            "deep_problem_research": {
                "evidence_count": 3,
            },
        },
        {
            "company": "Lyzr AI",
            "company_url_basis": "watchlist",
            "deep_problem_research": {
                "evidence_count": 0,
            },
        },
        {
            "company": "SomeVC-Funded Startup",
            "company_url_basis": "reviewed_registry_exact_company_name",
            "deep_problem_research": {
                "evidence_count": 2,
            },
        },
    ]

    rendered = _watchlist_movement_section(discovered)

    # Only watchlist companies should appear
    assert "Emergent" in rendered
    assert "Lyzr AI" in rendered
    assert "SomeVC-Funded Startup" not in rendered
    assert "3 signals found" in rendered
    assert "no activity observed" in rendered


def test_watchlist_movement_section_handles_empty_list():
    """Empty watchlist returns honest message."""
    rendered = _watchlist_movement_section([])
    assert "No watchlist companies present" in rendered


def test_problem_brief_block_includes_all_sections():
    """A single problem brief block includes signals, hypothesis, prompt, contact, and drafts."""
    company = {
        "company": "TestCorp",
        "deep_problem_research": {
            "observed_signals": [
                {
                    "text": "We need better automation",
                    "url": "https://example.com/post1",
                },
                {
                    "text": "Manual processes slow us down",
                    "url": "https://example.com/post2",
                },
            ],
            "problem_hypothesis": "The team struggles with manual workflows.",
            "evidence_count": 5,
        },
        "prompt_generation": {
            "prompt_text": "Build an automation tool for TestCorp's workflow...",
            "prompt_basis": "multiple_urls",
        },
        "selected_contact": {
            "name": "Jane Smith",
            "email": "jane@testcorp.com",
            "linkedin": "https://linkedin.com/in/janesmith",
            # The keys choose_contact actually emits.
            "source_url": "https://testcorp.com/team",
            "access_date": "2026-09-13",
        },
        "outreach": {
            "email_body": "Hi Jane, I noticed...",
            "linkedin_note": "I'm interested in TestCorp's automation challenges.",
            "linkedin_message": "Following up on our connection...",
            "send_status": "ready",
        },
    }

    lines = _problem_brief_block(company)
    text = "\n".join(lines)

    # All sections should be present
    assert "### TestCorp" in text
    assert "**Observed signals:**" in text
    assert "We need better automation" in text
    assert "https://example.com/post1" in text
    assert "**Inference (not verified):**" in text
    assert "The team struggles with manual workflows." in text
    assert "**Claude Code prompt (paste-ready):**" in text
    assert "Build an automation tool for TestCorp's workflow..." in text
    assert "**Contact:**" in text
    assert "Jane Smith" in text
    assert "jane@testcorp.com" in text
    assert "https://linkedin.com/in/janesmith" in text
    # Provenance is mandatory on a contact, so the digest must print it.
    assert "https://testcorp.com/team" in text
    assert "2026-09-13" in text
    assert "**Outreach drafts:**" in text
    assert "Hi Jane, I noticed..." in text
    assert "I'm interested in TestCorp's automation challenges." in text


def test_problem_brief_block_handles_insufficient_evidence_prompt():
    """When prompt_text is empty due to insufficient evidence, show honest message."""
    company = {
        "company": "NoEvidenceCorp",
        "deep_problem_research": {
            "observed_signals": [],
            "problem_hypothesis": "",
            "evidence_count": 0,
        },
        "prompt_generation": {
            "prompt_text": "",
            "prompt_basis": "insufficient_evidence",
        },
        "selected_contact": {
            "status": "contact_research_required",
        },
        "outreach": {
            "send_status": "blocked_insufficient_evidence",
        },
    }

    lines = _problem_brief_block(company)
    text = "\n".join(lines)

    # Should show honest message, not empty fence
    assert "Insufficient evidence to generate a prompt" in text
    assert "```" not in text or text.count("```") == 0


def test_problem_brief_block_shows_blocked_validation_errors():
    """Blocked outreach drafts show why they failed validation."""
    company = {
        "company": "BadDraftCorp",
        "deep_problem_research": {
            "observed_signals": [{"text": "Some problem", "url": "https://example.com"}],
            "problem_hypothesis": "A hypothesis",
        },
        "prompt_generation": {
            "prompt_text": "A good prompt",
        },
        "selected_contact": {
            "name": "Someone",
            "email": "someone@example.com",
        },
        "outreach": {
            "send_status": "blocked_validation",
            "validation_errors": [
                "contains_em_dash",
                "contains_word_leverage",
            ],
        },
    }

    lines = _problem_brief_block(company)
    text = "\n".join(lines)

    # Should show why blocked
    assert "Blocked by humanizer rules" in text
    assert "contains_em_dash" in text
    assert "contains_word_leverage" in text


def test_problem_briefs_section_empty_list_says_so():
    """Empty problem briefs list says so honestly."""
    rendered = _problem_briefs_section([])
    assert "No companies were researched" in rendered


def test_problem_briefs_section_renders_multiple_companies():
    """Multiple companies each get their own block."""
    discovered = [
        {
            "company": "Company A",
            "company_url_basis": "watchlist",
            "deep_problem_research": {
                "observed_signals": [{"text": "Problem A", "url": "https://a.com"}],
                "problem_hypothesis": "Hypothesis A",
            },
            "prompt_generation": {"prompt_text": "Prompt A"},
            "selected_contact": {"name": "Contact A", "email": "a@example.com"},
            "outreach": {"send_status": "ready"},
        },
        {
            "company": "Company B",
            "company_url_basis": "reviewed_registry_exact_company_name",
            "deep_problem_research": {
                "observed_signals": [{"text": "Problem B", "url": "https://b.com"}],
                "problem_hypothesis": "Hypothesis B",
            },
            "prompt_generation": {"prompt_text": "Prompt B"},
            "selected_contact": {"name": "Contact B", "email": "b@example.com"},
            "outreach": {"send_status": "ready"},
        },
    ]

    rendered = _problem_briefs_section(discovered)

    # Both companies should appear
    assert "### Company A" in rendered
    assert "### Company B" in rendered
    assert "Problem A" in rendered
    assert "Problem B" in rendered
    assert "Hypothesis A" in rendered
    assert "Hypothesis B" in rendered


def test_fixture_pipeline_render_includes_discovered_section(tmp_path: Path, monkeypatch) -> None:
    """Integration: real pipeline output feeds into render_digest and sections appear.

    This is the key integration test: we run the actual pipeline with fixtures,
    mock the deep research/prompt generation to add discovered_for_research,
    then render the digest and verify real content is present.
    """
    monkeypatch.setenv("ENABLE_BEDROCK", "false")
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")
    health = fixture_health(len(records))

    # Mock deep research and prompt generation to inject test data into the pipeline
    discovered_test_data = [
        {
            "company": "Test Watchlist Co",
            "company_url": "https://test-watchlist.com",
            "company_url_basis": "watchlist",
            "lane": "ai",
            "funding_event_id": "watchlist_test_1",
            "source": "watchlist",
            "deep_problem_research": {
                "problem_status": "inference_needs_validation",
                "evidence_count": 3,
                "observed_signals": [
                    {
                        "text": "Users report slow performance",
                        "url": "https://test-watchlist.com/blog/perf",
                    },
                ],
                "problem_hypothesis": "The platform has performance bottlenecks.",
                "why_now": "Growing user base is hitting scaling limits.",
                "confidence": "medium",
                "supported": True,
            },
            "prompt_generation": {
                "prompt_text": "Build a performance monitoring dashboard for Test Watchlist Co.",
                "prompt_basis": "multiple_urls",
            },
            "selected_contact": {
                "name": "Test Contact",
                "email": "contact@test-watchlist.com",
                "linkedin": "https://linkedin.com/in/testcontact",
                "source": "company_team_page",
            },
            "outreach": {
                "email_subject": "watchlist prototype idea",
                "email_body": (
                    "Hi Test Contact, I've been researching Test Watchlist Co and found a "
                    "concrete operational gap worth flagging: users report slow performance "
                    "on the platform. I put together a small working prototype instead of "
                    "just describing the idea, since a runnable demo says more than a "
                    "pitch. I'm looking for a six-month onsite generalist internship in "
                    "Bengaluru starting November 2026, where I can pick up real "
                    "cross-functional work like this. Would it be useful to walk through "
                    "the prototype together sometime this week?"
                ),
                "linkedin_note": "Interested in your performance work",
                "linkedin_message": "Great to connect! Here's my prototype idea.",
                "send_status": "draft_needs_human_review",
                "draft_source": "problem_led",
                "validation_errors": [],
            },
        }
    ]

    # Patch select_discovered_for_research to return our test data
    def mock_select(*args, **kwargs):
        return discovered_test_data

    def mock_build_prompts(companies, **kwargs):
        # Prompts are already in test data
        return companies

    def mock_research_deep(company, **kwargs):
        return company.get("deep_problem_research", {})

    def mock_choose_contact(company):
        return company.get("selected_contact")

    def mock_draft_outreach(company):
        return company.get("outreach", {})

    monkeypatch.setattr(
        "pipeline.select_discovered_for_research",
        mock_select,
    )
    monkeypatch.setattr(
        "pipeline.build_prompts_for_companies",
        mock_build_prompts,
    )
    monkeypatch.setattr(
        "pipeline.research_deep_problem",
        mock_research_deep,
    )
    monkeypatch.setattr(
        "pipeline.choose_contact",
        mock_choose_contact,
    )
    monkeypatch.setattr(
        "pipeline.draft_outreach",
        mock_draft_outreach,
    )

    run = run_pipeline(records, health, date(2026, 9, 8), config, tmp_path / "run")
    rendered = render_digest(run)

    # Verify watchlist movement section exists and has the company
    assert "## Watchlist movement" in rendered
    assert "Test Watchlist Co" in rendered

    # Verify problem briefs section exists
    assert "## Problem briefs for researched companies" in rendered

    # Verify full company block content is present
    assert "### Test Watchlist Co" in rendered
    assert "Users report slow performance" in rendered
    assert "https://test-watchlist.com/blog/perf" in rendered
    assert "The platform has performance bottlenecks." in rendered
    assert "**Claude Code prompt (paste-ready):**" in rendered
    assert "Build a performance monitoring dashboard" in rendered
    assert "contact@test-watchlist.com" in rendered

    # Regression: Gmail renders the HTML part over the plain-text part when
    # both exist, so the same content added to render_digest above must also
    # reach render_html_digest, not just the plain-text digest -- an earlier
    # version of this fix only touched render_digest and the HTML digest
    # actually sent to Daksh's inbox stayed unchanged.
    html_rendered = render_html_digest(run)
    assert "Watchlist movement" in html_rendered
    assert "Test Watchlist Co" in html_rendered
    assert "Users report slow performance" in html_rendered
    assert "The platform has performance bottlenecks." in html_rendered
    assert "Build a performance monitoring dashboard" in html_rendered
    assert "contact@test-watchlist.com" in html_rendered
    assert "Interested in your performance work" in html_rendered


def test_digest_quiet_day_with_no_discovered_companies(tmp_path: Path, monkeypatch) -> None:
    """A quiet day with no research still sends mail and says so (regression test).

    This ensures the 2026-09-12 fix (quiet days don't suppress mail) still works
    after Phase 7 restructuring.
    """
    monkeypatch.setenv("ENABLE_BEDROCK", "false")
    config = load_all()
    records = load_json_records(AUTOMATION_ROOT / "fixtures" / "opportunities.json", "fixture")
    health = fixture_health(len(records))

    # Mock select_discovered_for_research to return empty list (quiet day)
    def mock_select(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "pipeline.select_discovered_for_research",
        mock_select,
    )

    run = run_pipeline(records, health, date(2026, 9, 8), config, tmp_path / "run")
    rendered = render_digest(run)

    # Even on a quiet day, sections should be present
    assert "## Watchlist movement" in rendered
    assert "## Problem briefs for researched companies" in rendered
    # And should say what happened honestly
    assert "No watchlist companies" in rendered or "no activity" in rendered.lower()

    # HTML digest must stay honest on a quiet day too, not just plain text.
    html_rendered = render_html_digest(run)
    assert "Problem briefs" in html_rendered
    assert "No companies cleared deep research today" in html_rendered
    assert "No companies were researched" in rendered
