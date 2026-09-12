import json
from pathlib import Path

import pytest

from fetch_sources import (
    _ashby,
    _ftb,
    _greenhouse,
    _lever,
    _rise_sheet,
    _teamtailor,
    _verified_ats_url,
    _wellfound,
    _workable,
    _wwr,
    _yc,
    fetch_harvested_boards,
    harvest_ats_boards,
    watchlist_board_sources,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_rise_sheet_adapter_preserves_public_post_provenance() -> None:
    csv_text = (
        "Title,Type,Timing,Description,Stipend,Duration,Experience,Location,Deadline,Tags,"
        "HiringOrganization,HiringManager,Post URL,Apply Link,Contact Email,Date Added,"
        "Subchips,Similar Fields,PostedDate\n"
        "Founder's Office Intern,Hybrid,Full-time,Work with founders,20000,6 months,,"
        "Bangalore,,,Example Labs,,https://linkedin.com/posts/1,https://example.com/apply,,"
        "2026-09-10,,,2026-09-10\n"
    )
    records = _rise_sheet(csv_text, {"id": "rise_public_sheet", "source_priority": 1})
    assert len(records) == 1
    assert records[0]["verification_status"] == "machine_collected_unverified"
    assert records[0]["source_url"] == "https://linkedin.com/posts/1"


def test_ftb_contract_fixture() -> None:
    payload = json.loads((FIXTURES / "ftb-response.json").read_text(encoding="utf-8"))
    records = _ftb(
        payload,
        {"id": "ftb_internships", "url": "https://www.ftbhustle.com/api/internships"},
    )
    assert len(records) == 1
    assert records[0]["hiringOrganization"] == "Fixture Labs"
    assert records[0]["source_confidence"] == "official"


def test_wwr_contract_fixture() -> None:
    content = (FIXTURES / "wwr-feed.xml").read_bytes()
    records = _wwr(
        content,
        {"id": "wwr_rss", "url": "https://weworkremotely.com/remote-jobs.rss"},
    )
    assert len(records) == 1
    assert records[0]["company"] == "Remote Fixture"
    assert records[0]["title"] == "Chief of Staff Intern"


def test_teamtailor_rss_parser_extracts_bengaluru_roles() -> None:
    """Teamtailor RSS feed parsing with location extraction."""
    content = (FIXTURES / "teamtailor-feed.xml").read_bytes()
    records = _teamtailor(
        content,
        {"id": "lyzr_teamtailor", "url": "https://careers.lyzr.ai/jobs.rss", "company": "Lyzr AI"},
    )
    # Should extract multiple roles from the feed
    assert len(records) >= 1
    # Should extract title and location from Teamtailor RSS fields
    bengaluru_roles = [r for r in records if "bengaluru" in r.get("location", "").lower()]
    assert len(bengaluru_roles) > 0
    # Check record structure
    assert all(r["source_confidence"] == "official" for r in records)
    assert all(r["source"] == "lyzr_teamtailor" for r in records)


def test_watchlist_board_sources_reads_configured_boards_only() -> None:
    """Watchlist companies with a board_url+board_adapter become fetchable
    source dicts; a company with no board (AEOS, bootstrapped, no ATS) is
    skipped rather than guessed at."""
    watchlist_config = {
        "companies": [
            {
                "name": "Emergent",
                "board_url": "https://boards-api.greenhouse.io/v1/boards/emergentlabsinc/jobs",
                "board_adapter": "greenhouse_ats",
                "site_url": "https://emergent.sh",
            },
            {
                "name": "Lyzr AI",
                "board_url": "https://careers.lyzr.ai/jobs.rss",
                "board_adapter": "teamtailor_ats",
                "site_url": "https://lyzr.ai",
            },
            {
                "name": "AEOS",
                "board_url": "",
                "board_adapter": "",
                "site_url": "https://www.aeoscompany.com",
            },
        ]
    }

    sources = watchlist_board_sources(watchlist_config)

    assert len(sources) == 2
    by_company = {s["company"]: s for s in sources}
    assert "AEOS" not in by_company
    assert by_company["Emergent"]["adapter"] == "greenhouse_ats"
    assert by_company["Emergent"]["url"] == watchlist_config["companies"][0]["board_url"]
    assert by_company["Lyzr AI"]["adapter"] == "teamtailor_ats"
    assert all(s["enabled"] for s in sources)


def test_yc_parser_ignores_navigation_and_extracts_company() -> None:
    html = """
    <a href="/jobs/role/software-engineer/bengaluru">Software Engineer</a>
    <ul><li>
      <a href="/companies/samora-ai"><span>Samora AI (W26)</span></a>
      <a href="/companies/samora-ai/jobs/abc-chief-of-staff">Chief of Staff Intern</a>
      <div>Internship • Operations • Bengaluru, KA, IN</div>
    </li></ul>
    """
    records = _yc(
        html,
        {"id": "yc_bengaluru", "url": "https://www.ycombinator.com/jobs"},
    )
    assert len(records) == 1
    assert records[0]["company"] == "Samora AI"
    assert records[0]["title"] == "Chief of Staff Intern"


def test_wellfound_parser_uses_public_next_data_contract() -> None:
    payload = {
        "props": {
            "pageProps": {
                "apolloState": {
                    "data": {
                        "StartupResult:1": {
                            "name": "Startup One",
                            "slug": "startup-one",
                            "companySize": "SIZE_11_50",
                            "highlightedJobListings": [{"__ref": "JobListingSearchResult:10"}],
                        },
                        "JobListingSearchResult:10": {
                            "id": "10",
                            "slug": "founders-office-intern",
                            "title": "Founder’s Office Intern",
                            "description": "Work with founders across growth and operations.",
                            "locationNames": ["Bengaluru"],
                            "jobType": "internship",
                            "liveStartAt": 1788912000,
                            "remote": False,
                            "remoteConfig": {"kind": "ONSITE"},
                        },
                    }
                }
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    records = _wellfound(
        html,
        {"id": "wellfound_bengaluru", "url": "https://wellfound.com/location/bangalore"},
    )
    assert len(records) == 1
    assert records[0]["company"] == "Startup One"
    assert records[0]["title"] == "Founder’s Office Intern"
    assert records[0]["posted_at"]


@pytest.mark.parametrize(
    ("vendor", "adapter", "url", "expected_title"),
    [
        (
            "greenhouse",
            "greenhouse_ats",
            "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true",
            "Strategy Intern",
        ),
        ("lever", "lever_ats", "https://api.lever.co/v0/postings/example?mode=json", "Growth Operations Intern"),
        ("ashby", "ashby_ats", "https://api.ashbyhq.com/posting-api/job-board/example", "Founder Associate Intern"),
        (
            "workable",
            "workable_ats",
            "https://apply.workable.com/api/v3/accounts/example/jobs",
            "Business Operations Intern",
        ),
    ],
)
def test_official_ats_contract_fixtures(vendor, adapter, url, expected_title) -> None:
    payload = json.loads((FIXTURES / "ats-responses.json").read_text(encoding="utf-8"))[vendor]
    source = {
        "id": f"example_{vendor}",
        "adapter": adapter,
        "url": url,
        "company": "Example",
        "company_url": "https://example.com",
        "source_priority": 2,
    }
    parser = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby, "workable": _workable}[vendor]
    assert _verified_ats_url(source) == url
    records = parser(payload, source)
    assert len(records) == 1
    assert records[0]["company"] == "Example"
    assert records[0]["title"] == expected_title
    assert records[0]["location"]
    assert records[0]["source_confidence"] == "official"
    assert records[0]["source_url"].startswith("https://")


@pytest.mark.parametrize("url", ["", "http://api.lever.co/v0/postings/example", "https://example.com/jobs"])
def test_ats_adapter_rejects_missing_guessed_or_non_https_urls(url) -> None:
    with pytest.raises(ValueError, match="explicit reviewed"):
        _verified_ats_url({"adapter": "lever_ats", "url": url})


def test_spotted_leads_loader_keeps_only_unique_https_urls(tmp_path) -> None:
    from fetch_sources import load_spotted_leads

    path = tmp_path / "linkedin-leads.txt"
    path.write_text(
        "# comment\n"
        "\n"
        "https://www.linkedin.com/posts/example-founder-office\n"
        "https://www.linkedin.com/posts/example-founder-office\n"
        "not a url\n"
        "ftp://example.com/file\n"
        "http://example.com/internship\n",
        encoding="utf-8",
    )
    records = load_spotted_leads(path)
    assert [item["source_url"] for item in records] == [
        "https://www.linkedin.com/posts/example-founder-office",
        "http://example.com/internship",
    ]
    assert all(item["source"] == "human_spotted" for item in records)
    assert all(item["verification_status"] == "human_spotted_unverified" for item in records)
    assert all(not item["company"] and not item["title"] for item in records)
    again = load_spotted_leads(path)
    assert [item["id"] for item in again] == [item["id"] for item in records]


HARVEST_HTML = """
<html><body>
<a href="https://boards.greenhouse.io/celonis/jobs/7817337003">Senior Engineer</a>
<a href="https://boards.greenhouse.io/celonis/jobs/7991442003">Engineer II</a>
<a href="https://jobs.ashbyhq.com/deliveroo/0ae399e2-1">Ops Associate</a>
<a href="https://acme.lever.co/abc-123">Growth Intern</a>
<a href="https://apply.workable.com/acme/j/xyz">Skipped vendor</a>
<a href="https://example.com/jobs">Not a board</a>
<a href="/relative/path">Relative</a>
</body></html>
"""


def test_harvest_converts_only_known_vendor_links() -> None:
    boards = harvest_ats_boards(HARVEST_HTML, 8)
    by_id = {item["id"]: item for item in boards}
    assert set(by_id) == {
        "ats_harvested_greenhouse_celonis",
        "ats_harvested_ashby_deliveroo",
        "ats_harvested_lever_acme",
    }
    assert by_id["ats_harvested_greenhouse_celonis"]["url"] == (
        "https://boards-api.greenhouse.io/v1/boards/celonis/jobs"
    )
    assert by_id["ats_harvested_ashby_deliveroo"]["url"] == (
        "https://api.ashbyhq.com/posting-api/job-board/deliveroo"
    )
    assert by_id["ats_harvested_lever_acme"]["url"] == (
        "https://api.lever.co/v0/postings/acme?mode=json"
    )
    assert all(item["adapter"].endswith("_ats") for item in boards)
    assert by_id["ats_harvested_greenhouse_celonis"]["company"] == "Celonis"


def test_harvest_dedupes_and_caps_boards() -> None:
    html = HARVEST_HTML + '<a href="https://boards.greenhouse.io/zeta/j/1">Z</a>'
    boards = harvest_ats_boards(html, 2)
    assert len(boards) == 2
    assert len({item["id"] for item in boards}) == 2


def test_harvest_rejects_malformed_slugs() -> None:
    html = '<a href="https://boards.greenhouse.io//jobs/1">Empty</a>'
    assert harvest_ats_boards(html, 8) == []


class _HarvestResponse:
    status_code = 200

    def __init__(self, text="", payload=None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _HarvestSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, timeout=0):
        self.calls.append(url)
        if url not in self.routes:
            raise RuntimeError("unexpected " + url)
        return self.routes[url]


def test_fetch_harvested_boards_flows_records_and_health() -> None:
    greenhouse_payload = json.loads(
        (FIXTURES / "ats-responses.json").read_text(encoding="utf-8")
    )["greenhouse"]
    session = _HarvestSession(
        {
            "https://jobs.accel.com/jobs": _HarvestResponse(text=HARVEST_HTML),
            "https://boards-api.greenhouse.io/v1/boards/celonis/jobs": _HarvestResponse(
                payload=greenhouse_payload
            ),
            "https://api.ashbyhq.com/posting-api/job-board/deliveroo": _HarvestResponse(
                payload={"jobs": []}
            ),
            "https://api.lever.co/v0/postings/acme?mode=json": _HarvestResponse(payload=[]),
        }
    )
    records, health = fetch_harvested_boards(
        session,
        {"enabled": True, "pages": ["https://jobs.accel.com/jobs"], "max_boards": 8},
        25,
        0,
    )
    by_source = {item["source"] for item in records}
    assert "ats_harvested_greenhouse_celonis" in by_source
    assert len(records) == 1
    assert records[0]["title"] == "Strategy Intern"
    statuses = {item["source_id"]: item["status"] for item in health}
    assert statuses["ats_harvested_greenhouse_celonis"] == "ok"
    assert statuses["ats_harvested_ashby_deliveroo"] == "zero_results"


def test_fetch_harvested_boards_respects_disabled_flag() -> None:
    session = _HarvestSession({})
    records, health = fetch_harvested_boards(session, {"enabled": False}, 25, 0)
    assert records == [] and health == []
    assert session.calls == []
