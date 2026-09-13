from datetime import date, datetime, timezone

import pipeline
from contacts import choose_contact
from gmail_outcomes import classify_reply, outcome_updates
from outreach import asks_for_no_ai, draft_outreach
from research import deterministic_research

RESSL_PAGE = (
    "GTM Intern\n"
    "This is a GTM role. You will spend most of your time just getting the right people on a call.\n"
    "I can not emphasise enough how negatively we view usage of AI in any kind of comms content.\n"
    "When reaching out, please highlight your GTM experience, do not use AI to write it."
)


def test_listing_page_is_read_from_apply_link_then_source_and_bounded() -> None:
    calls: list[str] = []

    def reader(url: str) -> str:
        calls.append(url)
        return "Own the partnerships pipeline end to end." if "apply" in url else ""

    records = [
        {"id": "a", "apply_url": "https://x.co/apply", "source_url": "https://x.co/post"},
        {"id": "b", "apply_url": "", "source_url": "https://y.co/post"},
        {"id": "c", "apply_url": "https://z.co/apply", "source_url": "https://z.co/post"},
    ]
    pipeline.attach_listing_pages(records, max_fetches=2, reader=reader)
    assert records[0]["listing_page_url"] == "https://x.co/apply"
    assert "listing_page_text" not in records[1]
    assert "listing_page_text" not in records[2]
    assert calls == ["https://x.co/apply", "https://y.co/post"]


def test_research_quotes_the_job_page_when_the_post_names_no_work() -> None:
    record = {
        "company": "SuprSend",
        "title": "Founder's Office Intern",
        "source_url": "https://www.linkedin.com/posts/x",
        "description": "We're hiring at SuprSend across 6 roles.",
        "listing_page_text": "Run cold outreach experiments: test channels, angles, and messaging.",
        "listing_page_url": "https://jobs.example.in/suprsend/1",
    }
    research = deterministic_research(record)
    assert research["observed_problem_signal"].startswith('The listing states: "Run cold outreach')
    assert research["observation_url"] == "https://jobs.example.in/suprsend/1"


def test_no_ai_request_blocks_drafting_and_prompt_carries_the_listing() -> None:
    record = {
        "company": "Ressl AI",
        "title": "GTM Intern",
        "source_url": "https://www.ycombinator.com/companies/ressl-ai/jobs/1",
        "description": "Ressl AI (W26) Train, eval and build autonomous agents",
        "listing_page_text": RESSL_PAGE,
        "listing_page_url": "https://www.ycombinator.com/companies/ressl-ai/jobs/1",
        "research": {"solution_concept": ""},
    }
    assert asks_for_no_ai(record) == "do not use ai"
    prompt = draft_outreach(record)["claude_prompt"]
    assert prompt.startswith("## Read first: this employer asked for no AI-written messages")
    assert "Do NOT draft the email" in prompt
    assert "## The listing, verbatim (source: https://www.ycombinator.com/companies/ressl-ai/jobs/1)" in prompt
    assert "negatively we view usage of AI" in prompt


def test_docs_placeholder_and_off_domain_addresses_are_not_contacts() -> None:
    contact = choose_contact({
        "company": "SuprSend",
        "company_url": "https://docs.suprsend.com",
        "deep_problem_research": {"published_emails": ["dev@company.com", "hello@suprsend.com"]},
    })
    assert contact["email"] == "hello@suprsend.com"
    assert choose_contact({
        "company": "Nobody",
        "research": {"published_emails": ["dev@company.com"]},
    })["status"] == "contact_research_required"


def test_info_mailbox_is_a_role_mailbox_not_a_person() -> None:
    contact = choose_contact({
        "company_url": "https://kplor.com",
        "research": {"published_emails": ["info@kplor.com"]},
    })
    assert contact["email"] == "info@kplor.com"
    assert contact["contact_priority"] == "fallback_generic"


class FakeGmail:
    def __init__(self, results: dict[str, list[dict]]):
        self.results = results
        self.queries: list[str] = []

    def find(self, query: str, limit: int = 5) -> list[dict]:
        self.queries.append(query)
        return next((value for key, value in self.results.items() if key in query), [])


def _message(message_id: str, day: str, to: str = "", subject: str = "", snippet: str = "") -> dict:
    millis = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)
    return {
        "id": message_id,
        "internalDate": str(millis),
        "snippet": snippet,
        "payload": {"headers": [{"name": "To", "value": to}, {"name": "Subject", "value": subject}]},
    }


def test_gmail_fills_sent_reply_and_invite_without_overwriting_daksh() -> None:
    gmail = FakeGmail({
        "in:sent to:tushar@suprsend.com": [_message("s1", "2026-09-14", to="tushar@suprsend.com")],
        "from:@suprsend.com": [_message("r1", "2026-09-16", subject="Re: partnerships", snippet="Could we schedule a call this week?")],
        "calendar-notification@google.com": [_message("c1", "2026-09-17")],
    })
    rows = [
        {"id": "o1", "company": "SuprSend", "contact_email": "tushar@suprsend.com",
         "send_status": "draft_needs_human_review"},
        {"id": "o2", "company": "Kplor", "contact_email": "a@kplor.com", "sent_at": "2026-09-10",
         "send_status": "sent_manually", "reply_outcome": "positive"},
    ]
    updates = outcome_updates(rows, gmail, date(2026, 9, 18))
    assert updates["o1"]["sent_at"] == "2026-09-14"
    assert updates["o1"]["send_status"] == "sent_manually"
    assert updates["o1"]["reply_outcome"] == "interview_requested"
    assert updates["o1"]["interview_outcome"] == "invited"
    assert updates["o1"]["outcome_basis"] == "sent_to_contact_email:s1; reply:r1; calendar_invite:c1"
    # Daksh's own values are never touched, and nothing is searched for them.
    assert "o2" not in updates or "reply_outcome" not in updates["o2"]
    assert not any("a@kplor.com" in query and "in:sent" in query for query in gmail.queries)


def test_gmail_without_contact_email_matches_company_in_subject_and_uses_free_mail_exactly() -> None:
    gmail = FakeGmail({
        'subject:"Auraaison"': [_message("s9", "2026-09-14", to="Founder <founder.auraaison@gmail.com>")],
        "from:founder.auraaison@gmail.com": [_message("r9", "2026-09-15", snippet="Unfortunately we have closed the role")],
    })
    updates = outcome_updates([{"id": "o9", "company": "Auraaison"}], gmail, date(2026, 9, 18))
    assert updates["o9"]["sent_at"] == "2026-09-14"
    assert updates["o9"]["reply_outcome"] == "rejected"
    assert not any("calendar-notification" in query for query in gmail.queries)


def test_classify_reply() -> None:
    assert classify_reply("Unfortunately we are not moving forward") == "rejected"
    assert classify_reply("Share your availability for an interview round") == "interview_requested"
    assert classify_reply("Thanks, will get back") == "replied"
