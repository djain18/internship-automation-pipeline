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

