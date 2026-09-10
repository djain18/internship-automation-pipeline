import firecrawl_research
from firecrawl_research import _relevant_to_company, _results, maybe_add_firecrawl_evidence


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

