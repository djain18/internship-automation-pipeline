from company_resolve import is_roundup_headline, resolve_company_urls


def test_roundup_headlines_detected() -> None:
    assert is_roundup_headline(
        "From Pixxel To Swish — Indian Startups Raised Over $321.9 Mn This Week"
    )
    assert is_roundup_headline("[Weekly funding roundup Sept 5-11] VC inflow doubles this week")
    assert is_roundup_headline("Indian startups raised $392M this week")


def test_single_company_headline_not_flagged_as_roundup() -> None:
    assert not is_roundup_headline("Nua raises $50 Mn to expand women's wellness portfolio")
    assert not is_roundup_headline("Graph AI raises $13.3M in Series A funding")


def _event(company: str, event_id: str) -> dict:
    return {"funding_event_id": event_id, "company": company}


def test_resolves_from_registry_pool() -> None:
    events = [_event("Nua", "e1")]
    registries = [{"company": "Nua", "company_url": "https://nua.in", "registry_url": "https://kalaari.com/portfolio"}]
    resolved = resolve_company_urls(events, registries, [])
    assert resolved[0]["company_url"] == "https://nua.in"
    assert resolved[0]["company_url_basis"] == "reviewed_registry_exact_company_name"


def test_resolves_from_same_run_opportunity_pool() -> None:
    # A company that is both hiring and freshly funded in the same run
    # resolves for free from its own apply-link-derived company_url.
    events = [_event("Ethereal Labs", "e1")]
    opportunities = [{"company": "Ethereal Labs", "company_url": "https://ethereallabs.com"}]
    resolved = resolve_company_urls(events, [], opportunities)
    assert resolved[0]["company_url"] == "https://ethereallabs.com"
    assert resolved[0]["company_url_basis"] == "same_run_opportunity_exact_company_name"


def test_registry_pool_checked_before_opportunity_pool() -> None:
    events = [_event("Nua", "e1")]
    registries = [{"company": "Nua", "company_url": "https://nua.in"}]
    opportunities = [{"company": "Nua", "company_url": "https://wrong-nua.example"}]
    resolved = resolve_company_urls(events, registries, opportunities)
    assert resolved[0]["company_url"] == "https://nua.in"


def test_unresolved_company_never_guesses_a_domain() -> None:
    events = [_event("Popo Global", "e1")]
    resolved = resolve_company_urls(events, [], [])
    assert not resolved[0].get("company_url")
    assert resolved[0]["company_url_basis"] == "unresolved"


def test_ambiguous_pool_match_is_not_resolved() -> None:
    events = [_event("Nua", "e1")]
    registries = [
        {"company": "Nua", "company_url": "https://nua.in"},
        {"company": "Nua", "company_url": "https://different-nua.example"},
    ]
    resolved = resolve_company_urls(events, registries, [])
    assert not resolved[0].get("company_url")
    assert resolved[0]["company_url_basis"] == "unresolved"
