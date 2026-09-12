"""Tests for deep problem research functionality."""

from datetime import date

import problem_research
from problem_research import research_deep_problem, select_discovered_for_research


def test_deep_research_requires_minimum_evidence(monkeypatch) -> None:
    """Insufficient evidence returns no hypothesis."""
    company = {
        "company": "Acme",
        "company_url": "https://acme.com",
        "lane": "ai",
    }
    config = {"deep_research_min_evidence": 2}

    # Mock to return no evidence
    def mock_fetch_site(*args, **kwargs):
        return [], []

    def mock_fetch_hn(*args, **kwargs):
        return []

    monkeypatch.setattr(problem_research, '_fetch_site_and_roles', mock_fetch_site)
    monkeypatch.setattr(problem_research, '_fetch_hackernews_evidence', mock_fetch_hn)

    result = research_deep_problem(
        company,
        llm_cache={},
        config=config,
        model_id="",
        region="",
    )

    # With no evidence and no LLM, should return insufficient_evidence
    assert result["problem_status"] == "insufficient_evidence"
    assert result["evidence_count"] == 0
    assert result["problem_hypothesis"] == ""


def test_deep_research_with_company_url_only() -> None:
    """Company with unresolved URL skips deep research."""
    company = {
        "company": "UnresolvedCorp",
        "lane": "unknown",
    }

    result = research_deep_problem(
        company,
        config={},
        model_id="",
        region="",
    )

    assert result["problem_status"] == "insufficient_evidence"
    assert result["evidence_count"] == 0


def test_deep_research_evidence_only_mode(monkeypatch) -> None:
    """Returns evidence without LLM when LLM disabled."""
    company = {
        "company": "Acme",
        "company_url": "https://acme.com",
        "lane": "ai",
    }
    config = {"deep_research_min_evidence": 1}

    # Mock to return evidence
    def mock_fetch_site(*args, **kwargs):
        return [
            {
                "url": "https://acme.com/about",
                "observation": "We build AI solutions",
                "access_date": "2026-09-12",
                "confidence": "medium",
                "basis": "company_site",
            }
        ], []

    def mock_fetch_hn(*args, **kwargs):
        return []

    monkeypatch.setattr(problem_research, '_fetch_site_and_roles', mock_fetch_site)
    monkeypatch.setattr(problem_research, '_fetch_hackernews_evidence', mock_fetch_hn)

    result = research_deep_problem(
        company,
        llm_cache={},
        config=config,
        model_id="",
        region="",
    )

    # Evidence-only mode
    assert result["problem_status"] == "evidence_only"
    assert result["evidence_count"] == 1
    assert result["problem_hypothesis"] == ""
    assert len(result.get("observed_signals", [])) > 0


def test_select_discovered_filters_by_company_url() -> None:
    """Companies without resolved company_url are excluded from selection."""
    companies = [
        {
            "company": "Resolved Inc",
            "company_url": "https://resolved.com",
            "company_url_basis": "reviewed_registry_exact_company_name",
            "lane": "ai",
        },
        {
            "company": "Unresolved Corp",
            "lane": "consumer",
        },
        {
            "company": "Another Resolved",
            "company_url": "https://another.com",
            "company_url_basis": "same_run_opportunity_exact_company_name",
            "lane": "unknown",
        },
    ]

    selected = select_discovered_for_research(
        companies,
        config={"max_deep_research_per_run": 8},
        run_date=date.today(),
    )

    # Should select only companies with resolved company_url
    selected_names = {c.get("company") for c in selected}
    assert "Resolved Inc" in selected_names
    assert "Another Resolved" in selected_names
    assert "Unresolved Corp" not in selected_names


def test_select_discovered_respects_max_per_run() -> None:
    """Selection respects max_deep_research_per_run cap."""
    companies = [
        {
            "company": f"Company {i}",
            "company_url": f"https://company{i}.com",
            "company_url_basis": "reviewed_registry_exact_company_name",
            "lane": "ai" if i % 2 == 0 else "consumer",
        }
        for i in range(15)
    ]

    selected = select_discovered_for_research(
        companies,
        config={"max_deep_research_per_run": 5},
        run_date=date.today(),
    )

    assert len(selected) <= 5


def test_sector_bonus_applied_correctly() -> None:
    """AI and consumer lanes get bonus; unknown with software terms also gets bonus."""
    ai_bonus = problem_research._apply_sector_bonus("ai", False)
    consumer_bonus = problem_research._apply_sector_bonus("consumer", False)
    unknown_no_terms = problem_research._apply_sector_bonus("unknown", False)
    unknown_with_terms = problem_research._apply_sector_bonus("unknown", True)

    assert ai_bonus == 1.0
    assert consumer_bonus == 1.0
    assert unknown_no_terms == 0.0
    assert unknown_with_terms == 0.5


def test_evidence_scoring_by_volume_and_recency() -> None:
    """Evidence score increases with volume and recent dates."""
    today = date.today()

    # Two pieces of evidence from recent dates
    evidence_recent = [
        {
            "observation": "Signal 1",
            "url": "https://example.com/1",
            "access_date": today.isoformat(),
            "basis": "company_site",
        },
        {
            "observation": "Signal 2",
            "url": "https://example.com/2",
            "access_date": today.isoformat(),
            "basis": "hacker_news",
        },
    ]

    # One piece of evidence from 365+ days ago
    evidence_old = [
        {
            "observation": "Old signal",
            "url": "https://example.com/old",
            "access_date": "2025-01-01",
            "basis": "company_site",
        },
    ]

    score_recent = problem_research._score_evidence(evidence_recent, today, "ai")
    score_old = problem_research._score_evidence(evidence_old, today, "ai")

    # Recent evidence should score higher
    assert score_recent > score_old
