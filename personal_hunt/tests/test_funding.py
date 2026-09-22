from datetime import date
from pathlib import Path

import pytest

from funding import (
    RoundupFormatChanged,
    load_ledger,
    parse_funding_feed,
    parse_funding_roundup_feed,
    save_ledger,
    select_funding_events,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
ENTRACKR = {"id": "entrackr_rss", "name": "Entrackr", "source_confidence": "medium"}
GALORE = {"id": "inc42_funding_galore", "name": "Inc42 Funding Galore", "source_confidence": "medium"}


def test_funding_feed_requires_dated_funding_assertion() -> None:
    xml = b"""<?xml version='1.0'?><rss version='2.0'><channel>
    <item><title>FreshCo raises $2 Mn in seed round</title>
    <link>https://example.com/fresh</link><pubDate>Wed, 09 Sep 2026 01:00:00 GMT</pubDate>
    <description>FreshCo announced a seed funding round.</description></item>
    <item><title>OldCo launches a feature</title><link>https://example.com/launch</link>
    <pubDate>Wed, 09 Sep 2026 01:00:00 GMT</pubDate></item>
    </channel></rss>"""
    records = parse_funding_feed(
        xml,
        {"id": "funding_fixture", "name": "Funding Fixture", "source_confidence": "medium"},
    )
    assert len(records) == 1
    assert records[0]["company"] == "FreshCo"
    assert records[0]["event_date"] == "2026-09-09"


def test_funding_feed_rejects_multi_company_roundup_headline() -> None:
    # 2026-09-12 incident: "From Pixxel To Swish - Indian Startups Raised
    # Over $321.9 Mn This Week" produced a bogus company named "From Pixxel
    # To Swish". Real Inc42/YourStory titles verified before this test.
    xml = """<?xml version='1.0'?><rss version='2.0'><channel>
    <item><title>From Pixxel To Swish — Indian Startups Raised Over $321.9 Mn This Week</title>
    <link>https://inc42.com/buzz/roundup</link><pubDate>Wed, 09 Sep 2026 01:00:00 GMT</pubDate>
    <description>Roundup text.</description></item>
    <item><title>[Weekly funding roundup Sept 5-11] VC inflow doubles this week</title>
    <link>https://yourstory.com/roundup</link><pubDate>Wed, 09 Sep 2026 01:00:00 GMT</pubDate>
    <description>Roundup text.</description></item>
    <item><title>Nua raises $50 Mn to expand women's wellness portfolio</title>
    <link>https://inc42.com/buzz/nua</link><pubDate>Wed, 09 Sep 2026 01:00:00 GMT</pubDate>
    <description>Single company article.</description></item>
    </channel></rss>""".encode("utf-8")
    records = parse_funding_feed(
        xml,
        {"id": "funding_fixture", "name": "Funding Fixture", "source_confidence": "medium"},
    )
    assert len(records) == 1
    assert records[0]["company"] == "Nua"


def test_funding_feed_repairs_mojibaked_title() -> None:
    xml = (
        "<?xml version='1.0'?><rss version='2.0'><channel>"
        "<item><title>Auraaisonâ€™s raises $2 Mn in seed round</title>"
        "<link>https://example.com/mojibake</link><pubDate>Wed, 09 Sep 2026 01:00:00 GMT</pubDate>"
        "<description>Company text.</description></item>"
        "</channel></rss>"
    ).encode("utf-8")
    records = parse_funding_feed(
        xml,
        {"id": "funding_fixture", "name": "Funding Fixture", "source_confidence": "medium"},
    )
    assert len(records) == 1
    assert "â€™" not in records[0]["headline"]
    assert "’" in records[0]["headline"]


def test_funding_feed_repairs_mojibaked_rupee_sign() -> None:
    # 2026-09-13: a real cloud run showed the apostrophe-only mojibake
    # check missed this pattern entirely -- U+20B9 (rupee) mis-decoded as
    # cp1252 produces U+00E2 U+201A U+00B9, not the U+00E2 U+20AC prefix
    # the first fix checked for. Verified against real Inc42 output:
    # "Paris Panini Parent Popo Global Raises â‚¹532 Cr
    # From Artal Asia" survived the earlier version of this fix unrepaired.
    xml = (
        "<?xml version='1.0'?><rss version='2.0'><channel>"
        "<item><title>Popo Global Raises â‚¹532 Cr From Artal Asia</title>"
        "<link>https://example.com/rupee</link><pubDate>Wed, 09 Sep 2026 01:00:00 GMT</pubDate>"
        "<description>Restaurant company hasâ€¦ raised funding.</description></item>"
        "</channel></rss>"
    ).encode("utf-8")
    records = parse_funding_feed(
        xml,
        {"id": "funding_fixture", "name": "Funding Fixture", "source_confidence": "medium"},
    )
    assert len(records) == 1
    assert "₹" in records[0]["headline"]
    assert "â" not in records[0]["headline"]
    assert "â" not in records[0]["source_reported_detail"]


def test_entrackr_feed_names_the_funded_company_not_the_investor() -> None:
    # Live Entrackr feed saved 2026-09-22. Investor-led headlines ("Info Edge
    # leads ... round in Factrika") must name the startup; IPO and anchor-book
    # news ("NSE raises Rs 6,746 Cr from anchor investors") is not a raise.
    records = parse_funding_feed((FIXTURES / "entrackr-rss-2026-09-22.xml").read_bytes(), ENTRACKR)
    by_company = {record["company"]: record for record in records}
    for expected in ("Protein Pantry", "Definedge", "Drivn", "Disha", "Factrika", "DheyaTech", "TRUE ARTIS", "VerifAIX", "Kiddo"):
        assert expected in by_company, expected
    assert "NSE" not in by_company
    assert not any("Info Edge" in name or "Avaana" in name for name in by_company)
    assert by_company["Definedge"]["round_type"] == "Pre-Series A"
    assert by_company["Protein Pantry"]["amount"] == "Rs 9 Cr"


def test_funding_galore_table_gives_one_event_per_startup_row() -> None:
    records = parse_funding_roundup_feed(
        (FIXTURES / "inc42-funding-galore-feed-2026-09-22.xml").read_bytes(), GALORE
    )
    flam = next(record for record in records if record["company"] == "Flam")
    assert flam["event_date"] == "2026-09-15"
    assert flam["event_date_basis"] == "roundup_row_date"
    assert flam["amount"] == "$40 Mn"
    assert flam["round_type"] == "Series B"
    assert flam["source_url"].startswith("https://inc42.com/buzz/from-flam-to-verifaix")
    # The table footer ("Source: Inc42 ...") is not a company.
    assert not any(record["company"].startswith("Source") for record in records)
    # No company is ever named after the roundup headline.
    assert not any(record["company"].casefold().startswith("from ") for record in records)


def test_roundup_without_a_table_fails_loudly_instead_of_guessing() -> None:
    xml = b"""<?xml version='1.0'?><rss version='2.0' xmlns:content='http://purl.org/rss/1.0/modules/content/'><channel>
    <item><title>From A To B - Indian Startups Raised $9 Mn This Week</title>
    <link>https://inc42.com/buzz/a-to-b</link><pubDate>Sat, 19 Sep 2026 03:30:00 GMT</pubDate>
    <content:encoded><![CDATA[<p>No table this week.</p>]]></content:encoded></item>
    </channel></rss>"""
    with pytest.raises(RoundupFormatChanged):
        parse_funding_roundup_feed(xml, GALORE)


def test_fourteen_day_window_merges_outlets_into_one_event_per_company() -> None:
    entrackr = parse_funding_feed((FIXTURES / "entrackr-rss-2026-09-22.xml").read_bytes(), ENTRACKR)
    galore = parse_funding_roundup_feed(
        (FIXTURES / "inc42-funding-galore-feed-2026-09-22.xml").read_bytes(), GALORE
    )
    selected, excluded = select_funding_events(entrackr + galore, date(2026, 9, 22), {"funding_window_days": 14})
    names = [event["company"] for event in selected]
    assert len(names) == len(set(name.casefold() for name in names))
    assert len(selected) >= 20
    assert all(0 <= event["age_days"] <= 14 for event in selected)
    assert any(item["rejection_reason"] == "funding_event_over_14_days" for item in excluded)
    dheya = next(event for event in selected if event["company"] == "DheyaTech")
    # Reported by both outlets: both URLs kept, the table row's amount kept.
    assert len(dheya["corroborating_urls"]) == 2
    assert dheya["amount"]


def test_ledger_keeps_research_when_the_same_raise_is_fetched_again(tmp_path: Path) -> None:
    researched = {
        "funding_event_id": "funding_x",
        "company": "FreshCo",
        "event_date": "2026-09-15",
        "source_url": "https://entrackr.com/a",
        "corroborating_urls": ["https://entrackr.com/a"],
        "research_status": "researched",
        "prompt_generation": {"prompt_text": "Build X"},
    }
    path = tmp_path / "funding_ledger.json"
    save_ledger(path, [researched])
    refetched = {
        "funding_event_id": "funding_x",
        "company": "FreshCo",
        "event_date": "2026-09-17",
        "source_url": "https://inc42.com/b",
        "corroborating_urls": ["https://inc42.com/b"],
        "amount": "$2 Mn",
    }
    selected, _ = select_funding_events(load_ledger(path) + [refetched], date(2026, 9, 22), {})
    assert len(selected) == 1
    event = selected[0]
    assert event["prompt_generation"]["prompt_text"] == "Build X"
    assert event["event_date"] == "2026-09-15"
    assert event["amount"] == "$2 Mn"
    assert event["corroborating_urls"] == ["https://entrackr.com/a", "https://inc42.com/b"]
    # 15 days later the event ages out of the window.
    later, excluded = select_funding_events([event], date(2026, 9, 30), {"funding_window_days": 14})
    assert later == [] and excluded
