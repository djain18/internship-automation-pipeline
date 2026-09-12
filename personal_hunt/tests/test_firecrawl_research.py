import firecrawl_research
from firecrawl_research import (
    _relevant_to_company,
    _results,
    maybe_add_firecrawl_evidence,
    search_public_evidence,
)


def test_firecrawl_result_shapes() -> None:
    assert _results({"data": {"web": [{"url": "https://example.com"}]}}) == [
        {"url": "https://example.com"}
    ]
    assert _results({"data": [{"url": "https://example.com"}]}) == [
        {"url": "https://example.com"}
    ]
    assert _results({"unexpected": "shape"}) == []


def test_company_relevance_rejects_ambiguous_search_noise() -> None:
    assert _relevant_to_company(
        "Ressl AI", "Ressl AI revenue", "Company profile", "https://example.com/ressl"
    )
    assert not _relevant_to_company(
        "Ethereal Labs", "Influencer jobs", "Generic internship board", "https://example.com/jobs"
    )


def test_free_source_evidence_is_default_even_if_legacy_flag_is_true(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_FIRECRAWL_RESEARCH", "true")
    monkeypatch.delenv("PUBLIC_RESEARCH_PROVIDER", raising=False)
    monkeypatch.setattr(
        firecrawl_research,
        "search_public_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Firecrawl called")),
    )
    record = {"company": "Example", "evidence": [{"url": "https://example.com/job"}]}

    enriched, status = maybe_add_firecrawl_evidence(record)

    assert enriched == record
    assert status == "source_evidence_free"


def test_search_public_evidence_sends_one_query_no_scrape_and_tags_basis(monkeypatch) -> None:
    """2026-09-13: cut from 2 queries + scrapeOptions to 1 query, no scrape,
    to fit the free plan's credit budget now that this feeds a per-company
    call inside research_deep_problem. Also confirms the returned evidence
    carries `basis`, not just `type` -- problem_research.py's Kimi
    instruction reads `basis`, and the mismatch would have made this
    evidence silently invisible to the model even once wired in."""
    captured_payloads = []

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "url": "https://techcrunch.com/2026/acme-raises",
                        "title": "Acme Corp raises Series A",
                        "description": "Acme Corp is scaling its operations team fast.",
                    }
                ]
            }

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured_payloads.append(json)
        return _Response()

    monkeypatch.setattr(firecrawl_research.requests, "post", _fake_post)

    evidence = search_public_evidence("Acme Corp", "fake-key")

    assert len(captured_payloads) == 1, "must send exactly one search query, not two"
    assert "scrapeOptions" not in captured_payloads[0]
    assert len(evidence) == 1
    assert evidence[0]["basis"] == "public_company_research"

