import json
from pathlib import Path

from fetch_sources import _ftb, _rise_sheet, _wellfound, _wwr, _yc


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
    records = _rise_sheet(
        csv_text, {"id": "rise_public_sheet", "source_priority": 1}
    )
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
                            "highlightedJobListings": [
                                {"__ref": "JobListingSearchResult:10"}
                            ],
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
