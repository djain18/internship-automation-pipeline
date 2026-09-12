"""Tests for prototype prompt generation."""

import build_prompt
from build_prompt import build_prototype_prompt, validate_prototype_prompt


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
        "supported": True,
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


def test_generated_prompt_passes_its_own_validator(monkeypatch) -> None:
    """A real LLM-generated prompt, assembled from the ACTUAL on-disk
    template (templates/prototype_prompt.txt), must pass
    validate_prototype_prompt -- this is the check that would have caught
    the validator being written against the embedded PROMPT_TEMPLATE
    fallback's different headings ("## Problem") instead of the real
    template's ("## Observed signals", "## Build the prototype")."""
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setattr(
        build_prompt,
        "cached_bedrock_json",
        lambda **kwargs: (
            {
                "what_to_build": (
                    "An internal dashboard that surfaces support ticket volume "
                    "by team so leads can staff onboarding without guesswork."
                ),
                "stack_constraint": "Assume a Python/React stack; mark as an assumption.",
                "acceptance_criteria": ["Loads sample tickets", "Shows per-team counts"],
                "scope_hours": 4,
            },
            {"cache_key": "k"},
        ),
    )
    company = {"company": "Acme", "company_url": "https://acme.com"}
    problem_research = {
        "supported": True,
        "problem_hypothesis": "Scaling support strains the onboarding team.",
        "observed_signals": [
            {"text": "We help companies scale support", "url": "https://evidence.com/1"},
        ],
    }

    result = build_prototype_prompt(
        company, problem_research, llm_cache={}, model_id="moonshotai.kimi-k2.5", region="ap-south-1"
    )

    assert result["llm_status"] == "ok"
    assert result.get("validation_errors") is None
    errors = validate_prototype_prompt(result["prompt_text"], "Acme")
    assert errors == []


def test_unsupported_hypothesis_never_reaches_the_llm(monkeypatch) -> None:
    """Real-but-garbage evidence (the Lyzr AI cookie-consent banner) gives
    non-empty observed_signals while research_deep_problem correctly returned
    supported=false with an empty hypothesis. Requiring only evidence_urls let
    this invent a prototype anyway. The gate must fail closed BEFORE any model
    call -- cached_bedrock_json raises here, so a regression fails loudly."""
    def _explode(**kwargs):
        raise AssertionError("cached_bedrock_json called for an unsupported hypothesis")

    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setattr(build_prompt, "cached_bedrock_json", _explode)

    result = build_prototype_prompt(
        {"company": "Lyzr AI", "company_url": "https://lyzr.ai"},
        {
            "supported": False,
            "problem_hypothesis": "",
            "observed_signals": [
                {"text": "We use cookies to improve your experience", "url": "https://lyzr.ai/careers"},
            ],
        },
        llm_cache={},
        model_id="moonshotai.kimi-k2.5",
        region="ap-south-1",
    )

    assert result["llm_status"] == "skipped_unsupported_hypothesis"
    assert result["prompt_text"] == ""


def test_batch_prompt_generation() -> None:
    """Generate prompts for multiple companies, reading Phase 2's real key."""
    companies = [
        {
            "company": "Company A",
            "company_url": "https://a.com",
            "deep_problem_research": {
                "problem_hypothesis": "Problem A",
                "observed_signals": [
                    {"text": "Signal A", "url": "https://evidence.com/a"}
                ]
            }
        },
        {
            "company": "Company B",
            "company_url": "https://b.com",
            "deep_problem_research": {
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
    # Company A has an observed signal -> must find evidence, not skip empty
    assert results[0]["prompt_generation"]["evidence_urls"] == ["https://evidence.com/a"]
    assert results[0]["prompt_generation"]["llm_status"] != "skipped_no_evidence"
    # Company B has no signals -> correctly finds no evidence
    assert results[1]["prompt_generation"]["llm_status"] == "skipped_no_evidence"


def test_batch_prompt_generation_ignores_unrelated_problem_research_key() -> None:
    """A company carrying Phase 1's unrelated `problem_research` key (from
    research_funding_event, a different shape with no observed_signals)
    must not be mistaken for Phase 2's `deep_problem_research` output."""
    companies = [
        {
            "company": "Company C",
            "company_url": "https://c.com",
            "problem_research": {"observed_signal": "some funding headline"},
            "deep_problem_research": {
                "observed_signals": [
                    {"text": "Real signal", "url": "https://evidence.com/c"}
                ]
            },
        },
    ]

    results = build_prompt.build_prompts_for_companies(
        companies, llm_cache={}, model_id="", region=""
    )

    assert results[0]["prompt_generation"]["evidence_urls"] == ["https://evidence.com/c"]
