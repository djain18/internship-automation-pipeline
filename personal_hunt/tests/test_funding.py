from datetime import date

from funding import parse_funding_feed, select_funding_events


def _event(company: str, event_date: str, identifier: str) -> dict:
    return {
        "funding_event_id": identifier,
        "company": company,
        "event_date": event_date,
        "headline": f"{company} raises funding",
        "source_url": f"https://example.com/{identifier}",
        "corroborating_urls": [f"https://example.com/{identifier}"],
    }


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


def test_funding_primary_extension_and_hard_max() -> None:
    scoring = {
        "funding_primary_age_days": 15,
        "funding_extension_age_days": 30,
        "funding_primary_min_items": 3,
        "funding_max_items": 5,
    }
    records = [
        _event("FreshCo", "2026-09-01", "fresh"),
        _event("MonthCo", "2026-08-20", "month"),
        _event("TooOldCo", "2026-08-09", "old"),
    ]
    primary, extended, excluded = select_funding_events(
        records, date(2026, 9, 9), scoring
    )
    assert [item["company"] for item in primary] == ["FreshCo"]
    assert [item["company"] for item in extended] == ["MonthCo"]
    assert excluded[0]["rejection_reason"] == "funding_event_over_30_days"

