import json
from pathlib import Path

import pytest

from fetch_sources import (
    _ashby,
    _ftb,
    _greenhouse,
    _lever,
    _rise_sheet,
    _verified_ats_url,
    _wellfound,
    _workable,
    _wwr,
    _yc,
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
