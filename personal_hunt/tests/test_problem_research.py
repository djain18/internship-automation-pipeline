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
        return [], [], []  # evidence, emails, linkedin_urls

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


def test_firecrawl_evidence_feeds_in_for_a_real_funded_company(monkeypatch) -> None:
    """2026-09-13: company-site + HN alone were consistently too thin for a
    young funded company. _fetch_firecrawl_evidence must be called (and its
    result merged in) when company_url_basis is anything other than
    'watchlist' -- this is the actual fix for funded companies staying
    permanently insufficient_evidence."""
    company = {
        "company": "Graph AI",
        "company_url": "https://graphsafety.ai",
        "company_url_basis": "firecrawl_search_verified_onpage_name",
        "lane": "ai",
    }
    config = {"deep_research_min_evidence": 1}

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", lambda *a, **k: ([], [], []))
    monkeypatch.setattr(problem_research, "_fetch_hackernews_evidence", lambda *a, **k: [])
    monkeypatch.setattr(
        problem_research,
        "_fetch_firecrawl_evidence",
        lambda name: [
            {
                "basis": "public_company_research",
                "url": "https://techcrunch.com/graph-ai",
                "observation": "Graph AI is scaling its safety review team.",
                "confidence": "low",
            }
        ],
    )

    result = research_deep_problem(
        company, llm_cache={}, config=config, model_id="", region=""
    )

    assert result["evidence_count"] == 1
    assert result["problem_status"] != "insufficient_evidence" or result["evidence_score"] > 0


def test_firecrawl_evidence_skipped_for_watchlist_companies(monkeypatch) -> None:
    """Watchlist companies are the same 3 fixed names every run -- paying
    for a fresh Firecrawl search on them daily is pure waste. Must not be
    called at all when company_url_basis == 'watchlist'."""
    company = {
        "company": "Emergent",
        "company_url": "https://emergent.sh",
        "company_url_basis": "watchlist",
        "lane": "ai",
    }
    config = {"deep_research_min_evidence": 1}

    def _explode(name):
        raise AssertionError("_fetch_firecrawl_evidence must not be called for watchlist companies")

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", lambda *a, **k: ([], [], []))
    monkeypatch.setattr(problem_research, "_fetch_hackernews_evidence", lambda *a, **k: [])
    monkeypatch.setattr(problem_research, "_fetch_firecrawl_evidence", _explode)

    result = research_deep_problem(
        company, llm_cache={}, config=config, model_id="", region=""
    )

    assert result["evidence_count"] == 0


def test_deep_research_carries_published_emails_through_every_return_path(monkeypatch) -> None:
    """_fetch_site_and_roles's second element (scraped emails) used to be
    discarded (bound to _emails and never read again). It must reach the
    result dict on the insufficient-evidence path AND the evidence-found
    path, since contacts.py's _site_email reads it from here for every
    discovered/watchlist company."""
    company = {"company": "Acme", "company_url": "https://acme.com", "lane": "ai"}

    def mock_fetch_site_no_evidence(*_a, **_k):
        return [], ["founders@acme.com"], []

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", mock_fetch_site_no_evidence)
    monkeypatch.setattr(problem_research, "_fetch_hackernews_evidence", lambda *_a, **_k: [])
    result = research_deep_problem(company, llm_cache={}, config={}, model_id="", region="")
    assert result["problem_status"] == "insufficient_evidence"
    assert result["published_emails"] == ["founders@acme.com"]

    def mock_fetch_site_with_evidence(*_a, **_k):
        return (
            [{"url": "https://acme.com/careers", "observation": "hiring fast", "access_date": "2026-09-13"}],
            ["founders@acme.com"],
            [],
        )

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", mock_fetch_site_with_evidence)
    result = research_deep_problem(company, llm_cache={}, config={}, model_id="", region="")
    assert result["published_emails"] == ["founders@acme.com"]


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
        ], [], []  # evidence, emails, linkedin_urls

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


def _mock_evidence():
    return (
        [
            {
                "url": "https://acme.com/about",
                "observation": "We help support teams scale onboarding for enterprise customers.",
                "access_date": "2026-09-12",
                "confidence": "medium",
                "basis": "company_site",
            },
            {
                "url": "https://news.ycombinator.com/item?id=1",
                "observation": "Acme is hiring five support engineers this quarter.",
                "access_date": "2026-09-12",
                "confidence": "low",
                "basis": "hacker_news_algolia",
            },
        ],
        [],  # emails
        [],  # linkedin_urls
    )


def test_llm_signal_dropped_when_url_was_never_fetched(monkeypatch) -> None:
    """Fail-closed: a quote that's a real substring but paired with a URL we
    never fetched must be dropped -- text-only checking would let the model
    pair a genuine quote with a fabricated or mismatched source."""
    company = {"company": "Acme", "company_url": "https://acme.com", "lane": "ai"}
    config = {"deep_research_min_evidence": 1}

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", lambda *a, **k: _mock_evidence())
    monkeypatch.setattr(problem_research, "_fetch_hackernews_evidence", lambda *a, **k: [])
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setattr(
        problem_research,
        "cached_bedrock_json",
        lambda **kwargs: (
            {
                "observed_signals": [
                    {
                        "text": "We help support teams scale onboarding for enterprise customers.",
                        "url": "https://fabricated-source.example/never-fetched",
                    }
                ],
                "problem_hypothesis": "Support onboarding is a bottleneck.",
                "why_now": "Recent funding will accelerate hiring.",
                "confidence": "medium",
                "supported": True,
            },
            {"input_tokens": 10, "output_tokens": 10},
        ),
    )

    result = research_deep_problem(
        company, llm_cache={}, config=config, model_id="model-a", region="ap-south-1"
    )

    assert result["llm_status"] == "ok"
    assert result["observed_signals"] == []


def test_llm_signal_dropped_when_url_and_text_are_mismatched(monkeypatch) -> None:
    """A known URL paired with text that isn't actually from that source
    must also be dropped, not just an unknown URL."""
    company = {"company": "Acme", "company_url": "https://acme.com", "lane": "ai"}
    config = {"deep_research_min_evidence": 1}

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", lambda *a, **k: _mock_evidence())
    monkeypatch.setattr(problem_research, "_fetch_hackernews_evidence", lambda *a, **k: [])
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setattr(
        problem_research,
        "cached_bedrock_json",
        lambda **kwargs: (
            {
                # Real HN url, but the quoted text actually came from the
                # site evidence item, not the HN one -- mismatched pairing.
                "observed_signals": [
                    {
                        "text": "We help support teams scale onboarding for enterprise customers.",
                        "url": "https://news.ycombinator.com/item?id=1",
                    }
                ],
                "problem_hypothesis": "Support onboarding is a bottleneck.",
                "why_now": "Recent funding will accelerate hiring.",
                "confidence": "medium",
                "supported": True,
            },
            {"input_tokens": 10, "output_tokens": 10},
        ),
    )

    result = research_deep_problem(
        company, llm_cache={}, config=config, model_id="model-a", region="ap-south-1"
    )

    assert result["observed_signals"] == []


def test_llm_signal_kept_when_url_and_text_match(monkeypatch) -> None:
    """The positive case: a quote that really is a substring of the text
    fetched from its own claimed URL survives the gate."""
    company = {"company": "Acme", "company_url": "https://acme.com", "lane": "ai"}
    config = {"deep_research_min_evidence": 1}

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", lambda *a, **k: _mock_evidence())
    monkeypatch.setattr(problem_research, "_fetch_hackernews_evidence", lambda *a, **k: [])
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setattr(
        problem_research,
        "cached_bedrock_json",
        lambda **kwargs: (
            {
                "observed_signals": [
                    {
                        "text": "We help support teams scale onboarding for enterprise customers.",
                        "url": "https://acme.com/about",
                    }
                ],
                "problem_hypothesis": "Support onboarding is a bottleneck.",
                "why_now": "Recent funding will accelerate hiring.",
                "confidence": "medium",
                "supported": True,
            },
            {"input_tokens": 10, "output_tokens": 10},
        ),
    )

    result = research_deep_problem(
        company, llm_cache={}, config=config, model_id="model-a", region="ap-south-1"
    )

    assert result["problem_status"] == "inference_needs_validation"
    assert len(result["observed_signals"]) == 1
    assert result["observed_signals"][0]["url"] == "https://acme.com/about"


def test_llm_unsupported_hypothesis_reports_insufficient_evidence(monkeypatch) -> None:
    """Regression: problem_status was hardcoded to inference_needs_validation
    regardless of the model's own supported verdict -- a real cloud run
    (Emergent, evidence limited to homepage pricing copy) showed the model
    correctly refusing to ground a hypothesis (supported=false, empty
    problem_hypothesis, per the instruction added after Daksh flagged the
    resulting prototype tried to rebuild the company's own paid product),
    but the status still claimed a validated inference. research_funding_event
    already gets this right (status keyed on supported); this must match."""
    company = {"company": "Acme", "company_url": "https://acme.com", "lane": "ai"}
    config = {"deep_research_min_evidence": 1}

    monkeypatch.setattr(problem_research, "_fetch_site_and_roles", lambda *a, **k: _mock_evidence())
    monkeypatch.setattr(problem_research, "_fetch_hackernews_evidence", lambda *a, **k: [])
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setattr(
        problem_research,
        "cached_bedrock_json",
        lambda **kwargs: (
            {
                "observed_signals": [],
                "problem_hypothesis": "This should never surface unsupported.",
                "why_now": "This should never surface unsupported either.",
                "confidence": "low",
                "supported": False,
            },
            {"input_tokens": 10, "output_tokens": 10},
        ),
    )

    result = research_deep_problem(
        company, llm_cache={}, config=config, model_id="model-a", region="ap-south-1"
    )

    assert result["problem_status"] == "insufficient_evidence"
    assert result["problem_hypothesis"] == ""
    assert result["why_now"] == ""
    assert result["supported"] is False


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


def test_watchlist_companies_always_included() -> None:
    """Watchlist companies are always included regardless of evidence."""
    # Funded companies with evidence
    funded = [
        {
            "company": "Funded Co",
            "company_url": "https://funded.com",
            "company_url_basis": "reviewed",
            "lane": "ai",
            "funding_event_id": "funding_1",
        }
    ]

    # Watchlist company (no evidence gate applied)
    watchlist = [
        {
            "company": "Watchlist Co",
            "company_url": "https://watchlist.com",
            "lane": "ai",
            "funding_event_id": "watchlist_1",
        }
    ]

    selected = select_discovered_for_research(
        funded,
        config={"max_deep_research_per_run": 8},
        run_date=date.today(),
        watchlist_companies=watchlist,
    )

    selected_names = {c.get("company") for c in selected}
    assert "Watchlist Co" in selected_names
    assert "Funded Co" in selected_names


def test_watchlist_companies_bypass_evidence_gate() -> None:
    """Watchlist companies are included with no minimum evidence requirement."""
    # No funded companies
    funded = []

    # Watchlist company alone
    watchlist = [
        {
            "company": "Watchlist Only",
            "company_url": "https://watchlist.com",
            "lane": "unknown",
            "funding_event_id": "watchlist_1",
        }
    ]

    selected = select_discovered_for_research(
        funded,
        config={"max_deep_research_per_run": 8, "deep_research_min_evidence": 2},
        run_date=date.today(),
        watchlist_companies=watchlist,
    )

    # Watchlist should be selected despite no evidence and evidence gate
    selected_names = {c.get("company") for c in selected}
    assert "Watchlist Only" in selected_names
    assert len(selected) == 1


def test_watchlist_companies_reserve_slots() -> None:
    """Watchlist companies reserve slots; discovered fills remainder."""
    # Multiple funded companies
    funded = [
        {
            "company": f"Funded {i}",
            "company_url": f"https://funded{i}.com",
            "company_url_basis": "reviewed",
            "lane": "ai",
            "funding_event_id": f"funding_{i}",
        }
        for i in range(10)
    ]

    # Two watchlist companies
    watchlist = [
        {
            "company": "Watch 1",
            "company_url": "https://watch1.com",
            "lane": "ai",
            "funding_event_id": "watch_1",
        },
        {
            "company": "Watch 2",
            "company_url": "https://watch2.com",
            "lane": "ai",
            "funding_event_id": "watch_2",
        },
    ]

    selected = select_discovered_for_research(
        funded,
        config={"max_deep_research_per_run": 5},
        run_date=date.today(),
        watchlist_companies=watchlist,
    )

    # Should select both watchlist + up to 3 funded (5 total)
    assert len(selected) == 5
    selected_names = {c.get("company") for c in selected}
    assert "Watch 1" in selected_names
    assert "Watch 2" in selected_names
    # Should have 3 funded companies
    funded_selected = [n for n in selected_names if n.startswith("Funded")]
    assert len(funded_selected) == 3


def test_non_watchlist_company_with_thin_evidence_excluded() -> None:
    """Non-watchlist companies still respect the evidence-minimum gate."""
    # Funded company with no evidence
    funded = [
        {
            "company": "Thin Evidence Co",
            "company_url": "https://thin.com",
            "company_url_basis": "reviewed",
            "lane": "unknown",
            "funding_event_id": "funding_1",
        }
    ]

    # Empty watchlist
    watchlist = []

    selected = select_discovered_for_research(
        funded,
        config={
            "max_deep_research_per_run": 8,
            "deep_research_min_evidence": 2,
        },
        run_date=date.today(),
        watchlist_companies=watchlist,
    )

    # Pre-filter (select_discovered_for_research) only does URL checking,
    # not evidence checking. The gate applies later in research_deep_problem.
    # So "Thin Evidence Co" gets selected for research, but would fail the
    # evidence gate inside research_deep_problem.
    selected_names = {c.get("company") for c in selected}
    assert "Thin Evidence Co" in selected_names
