from discover_companies import parse_registry


def test_registry_candidates_remain_unqualified() -> None:
    html = """
    <a href="/portfolio">Portfolio</a>
    <a href="https://startup.example">Useful Startup</a>
    <a href="https://linkedin.com/company/useful">LinkedIn</a>
    """
    records = parse_registry(html, "https://fund.example/portfolio")
    assert len(records) == 1
    assert records[0]["company"] == "Useful Startup"
    assert records[0]["status"] == "needs_company_verification"
    assert "Bengaluru" in records[0]["next_action"]

