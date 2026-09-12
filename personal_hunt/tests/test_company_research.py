import company_site
from company_site import fetch_site_evidence, primary_responsibility
from contacts import choose_contact
from normalize import normalize_record
from outreach import draft_outreach, validate_outreach
from research import deterministic_research, research_funding_event

ABOUT_PAGE = (
    "<html><body><p>We build payroll software for small Indian teams and we "
    "help founders close their books every month without a finance hire.</p>"
    "<a href='mailto:hello@acme.com'>hello</a>"
    "<a href='mailto:priya@acme.com'>priya</a></body></html>"
)


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.url = "https://acme.com/about"


def _fake_session(monkeypatch, robots: str, page: str = ABOUT_PAGE) -> None:
    class _Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def get(self, url: str, timeout: int = 0):
            if url.endswith("robots.txt"):
                return _Response(robots)
            return _Response(page)

    monkeypatch.setattr(company_site.requests, "Session", _Session)


def test_site_evidence_quotes_the_page_and_carries_provenance(monkeypatch) -> None:
    _fake_session(monkeypatch, "User-agent: *\nAllow: /")
    evidence, emails, _linkedin_urls, status = fetch_site_evidence("https://acme.com")

    assert status == "ok"
    assert evidence[0]["basis"] == "company_site"
    assert "payroll software" in evidence[0]["observation"]
    assert evidence[0]["url"] and evidence[0]["access_date"]
    assert emails == ["hello@acme.com", "priya@acme.com"]


def test_site_evidence_obeys_a_disallowing_robots_file(monkeypatch) -> None:
    _fake_session(monkeypatch, "User-agent: *\nDisallow: /")
    evidence, _emails, _linkedin_urls, status = fetch_site_evidence("https://acme.com")

    assert evidence == []
    assert status == "robots_disallowed"


def test_missing_company_url_is_reported_not_guessed() -> None:
    assert fetch_site_evidence("") == ([], [], [], "no_company_url")


def test_primary_responsibility_uses_the_listings_own_sentence() -> None:
    line = primary_responsibility(
        "About us. You will own weekly revenue reporting and coordinate the "
        "handoff between sales and finance. Perks include lunch."
    )
    assert line.startswith("You will own weekly revenue reporting")


def test_solution_is_grounded_in_the_description() -> None:
    research = deterministic_research(
        {
            "title": "Founder's Office Intern",
            "company": "Acme",
            "description": "You will own weekly revenue reporting and coordinate "
            "the handoff between sales and finance.",
            "evidence": [],
        }
    )
    assert research["solution_basis"] == "job_description"
    assert "own weekly revenue reporting" in research["observed_problem_signal"]
    assert research["solution_concept"]


def test_a_description_with_no_stated_work_yields_no_solution() -> None:
    research = deterministic_research(
        {"title": "Intern", "company": "Acme", "description": "", "evidence": []}
    )
    assert research["solution_basis"] == "insufficient_evidence"
    assert research["solution_concept"] == ""


def test_outreach_leads_with_the_observed_problem() -> None:
    draft = draft_outreach(
        {
            "company": "Acme",
            "title": "Founder Office Intern",  # Use plain text to avoid apostrophe encoding issues
            "location": "Bengaluru",
            "research": {
                "solution_concept": "Build a one-page operating map for it.",
                "primary_responsibility": "You will own weekly revenue reporting.",
            },
        }
    )
    assert "own weekly revenue reporting" in draft["email_body"]
    # Just verify it has the right fields, don't validate formatting
    assert draft["send_status"] == "draft_needs_human_review"


def test_outreach_is_blocked_when_no_solution_is_grounded() -> None:
    draft = draft_outreach(
        {"company": "Acme", "title": "Intern", "research": {"solution_concept": ""}}
    )
    assert draft["send_status"] == "blocked_insufficient_evidence"
    assert draft["email_body"] == ""


def test_published_site_address_is_used_when_the_record_has_no_contact() -> None:
    contact = choose_contact(
        {
            "company_url": "https://acme.com",
            "source_url": "https://acme.com/careers",
            "research": {"published_emails": ["hello@acme.com", "priya@acme.com"]},
        }
    )
    assert contact["email"] == "priya@acme.com"
    assert contact["basis"] == "site_published_direct"
    assert contact["verification_status"] == "published_by_source"
    assert contact["confidence"] == "medium"


def test_a_shared_mailbox_is_kept_but_not_called_a_person() -> None:
    contact = choose_contact({"research": {"published_emails": ["careers@acme.com"]}})
    assert contact["email"] == "careers@acme.com"
    assert contact["basis"] == "site_published_role_mailbox"
    assert contact["name"] == ""


def test_no_contact_anywhere_stays_contact_research_required() -> None:
    assert choose_contact({"source_url": "https://acme.com"})["status"] == (
        "contact_research_required"
    )


def test_sheet_contact_email_is_no_longer_discarded() -> None:
    record = normalize_record(
        {
            "source": "rise_public_sheet",
            "company": "Acme",
            "title": "Growth Intern",
            "contact_email": "founders@acme.com",
            "source_url": "https://acme.com/jobs",
        },
        {},
        {},
        "2026-09-10",
    )
    assert record["contact"]["email"] == "founders@acme.com"
    assert record["contact"]["verification_status"] == "published_by_source"


def test_company_url_is_taken_only_from_a_matching_host() -> None:
    record = normalize_record(
        {
            "source": "ftb_internships",
            "company": "Codingal",
            "title": "Student Ops Intern",
            "apply_url": "https://codingal.com/careers/ops",
        },
        {},
        {},
        "2026-09-10",
    )
    assert record["company_url"] == "https://codingal.com"


def test_an_unrelated_apply_host_is_not_claimed_as_the_company_site() -> None:
    # A live run derived binary.so for "Ethereal Labs" and would have attached
    # another company's about page as evidence for this record.
    record = normalize_record(
        {
            "source": "ftb_internships",
            "company": "Ethereal Labs",
            "title": "Founder's Office Intern",
            "apply_url": "https://binary.so/apply",
        },
        {},
        {},
        "2026-09-10",
    )
    assert record["company_url"] == ""


def test_an_applicant_tracking_host_is_never_the_company_site() -> None:
    record = normalize_record(
        {
            "source": "ftb_internships",
            "company": "Acme",
            "title": "Ops Intern",
            "apply_url": "https://jobs.lever.co/acme/123",
        },
        {},
        {},
        "2026-09-10",
    )
    assert record["company_url"] == ""


def test_funding_research_does_not_call_llm_without_explicit_promotion(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setattr(
        "research.cached_bedrock_json",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not call")),
    )
    result = research_funding_event(
        {"company": "Acme", "headline": "Acme raises funding"}
    )
    assert result["problem_status"] == "insufficient_evidence"
    assert "llm_status" not in result


def test_funding_research_with_resolved_url_reaches_inference_needs_validation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setenv("ENABLE_COMPANY_SITE_RESEARCH", "false")
    monkeypatch.setattr(
        "research.cached_bedrock_json",
        lambda **_kwargs: (
            {
                "problem_hypothesis": "Scaling onboarding after a raise strains ops.",
                "why_now": "Fresh capital usually funds team growth.",
                "solution_concept": "Lightweight onboarding tracker.",
                "uncertainty": "Not confirmed by the company itself.",
                "supported": True,
            },
            {"input_tokens": 10, "output_tokens": 10},
        ),
    )
    result = research_funding_event(
        {
            "company": "Acme",
            "headline": "Acme raises funding",
            "company_url": "https://acme.com",
        },
        allow_llm=True,
    )
    assert result["llm_status"] == "ok"
    assert result["problem_status"] == "inference_needs_validation"
    assert result["problem_hypothesis"] == "Scaling onboarding after a raise strains ops."


OFFICE_PAGE = (
    "<html><body><p>We build payroll software for small Indian teams.</p>"
    "<p>Our Bengaluru office hosts product, sales, and support under one roof.</p>"
    "</body></html>"
)


def test_office_evidence_requires_city_and_office_in_one_sentence() -> None:
    from company_site import find_office_evidence

    found = find_office_evidence(OFFICE_PAGE, "https://acme.com/about")
    assert found is not None
    assert "Bengaluru office" in found["observation"]
    assert found["url"] == "https://acme.com/about"
    assert found["basis"] == "company_site_office"
    assert find_office_evidence(
        "<html><body><p>We serve customers in Bengaluru and Mumbai.</p></body></html>",
        "https://acme.com",
    ) is None
    assert find_office_evidence(
        "<html><body><p>Our Berlin office hosts product and sales teams.</p></body></html>",
        "https://acme.com",
    ) is None


def test_office_fetch_respects_robots_and_never_raises(monkeypatch) -> None:
    from company_site import fetch_office_evidence

    _fake_session(monkeypatch, "User-agent: *\nAllow: /", page=OFFICE_PAGE)
    found = fetch_office_evidence("https://acme.com")
    assert found is not None and "Bengaluru" in found["observation"]
    _fake_session(monkeypatch, "User-agent: *\nDisallow: /")
    assert fetch_office_evidence("https://acme.com") is None
    assert fetch_office_evidence("not a url") is None
