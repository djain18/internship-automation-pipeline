"""Tests for prototype prompt generation."""

import build_prompt
from build_prompt import build_prototype_prompt


def test_prompt_requires_evidence_urls() -> None:
    """Prompt generation skipped without evidence URLs."""
    company = {
        "company": "Acme",
        "company_url": "https://acme.com",
    }
    problem_research = {}

    result = build_prototype_prompt(
        company,
        problem_research,
        llm_cache={},
        model_id="",
        region="",
    )

    assert result["llm_status"] == "skipped_no_evidence"
    assert result["prompt_text"] == ""


def test_prompt_skipped_without_company_name() -> None:
    """Prompt generation requires company name."""
    company = {
        "company_url": "https://unknown.com",
    }
    problem_research = {
        "observed_signals": [
            {"text": "Some signal", "url": "https://evidence.com/1"}
        ]
    }

    result = build_prototype_prompt(
        company,
        problem_research,
        llm_cache={},
        model_id="",
        region="",
    )

    assert result["prompt_text"] == ""


def test_prompt_generation_with_evidence() -> None:
    """Prompt generation succeeds with company name and evidence URLs."""
    company = {
        "company": "Acme",
        "company_url": "https://acme.com",
    }
    problem_research = {
        "problem_hypothesis": "Scaling to serve 10k users strains customer support.",
        "observed_signals": [
            {"text": "We help companies scale support", "url": "https://evidence.com/1"},
            {"text": "Our support team is growing fast", "url": "https://evidence.com/2"},
        ]
    }

    # Without LLM (model_id=""), should still generate based on template
    result = build_prototype_prompt(
        company,
        problem_research,
        llm_cache={},
        model_id="",
        region="",
    )

    assert result["llm_status"] == "skipped_disabled"
    assert result["evidence_urls"] == ["https://evidence.com/1", "https://evidence.com/2"]


def test_prompt_basis_reflects_evidence_count() -> None:
    """Prompt basis string encodes evidence URL count."""
    company = {
        "company": "TestCorp",
        "company_url": "https://test.com",
    }

    # Test with different evidence counts
    for url_count in [1, 2, 5]:
        problem_research = {
            "observed_signals": [
                {"text": f"Signal {i}", "url": f"https://evidence.com/{i}"}
                for i in range(url_count)
            ]
        }

        result = build_prototype_prompt(
            company,
            problem_research,
            llm_cache={},
            model_id="",
            region="",
        )

        # Basis should encode URL count
        assert f"{url_count}_urls" in result["prompt_basis"]


def test_batch_prompt_generation() -> None:
    """Generate prompts for multiple companies."""
    companies = [
        {
            "company": "Company A",
            "company_url": "https://a.com",
            "problem_research": {
                "problem_hypothesis": "Problem A",
                "observed_signals": [
                    {"text": "Signal A", "url": "https://evidence.com/a"}
                ]
            }
        },
        {
            "company": "Company B",
            "company_url": "https://b.com",
            "problem_research": {
                "problem_hypothesis": "Problem B",
                "observed_signals": []
            }
        },
    ]

    results = build_prompt.build_prompts_for_companies(
        companies,
        llm_cache={},
        model_id="",
        region="",
    )

    assert len(results) == 2
    assert results[0]["company"] == "Company A"
    assert results[1]["company"] == "Company B"
    # Check that prompt_generation was added
    assert "prompt_generation" in results[0]
    assert "prompt_generation" in results[1]
