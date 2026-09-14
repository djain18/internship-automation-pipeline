import json
import subprocess
import sys
from pathlib import Path

from check_draft import check_email_draft

BODY = (
    "Dear Auraaison team,\n\n"
    "Your post describes early work at Auraaison as the messy, real, unglamorous version of "
    "building an AI company. That line is the reason I am writing.\n\n"
    "I am Daksh Jain, a final-year BCA student at Christ University, Bengaluru. At Godel "
    "Earth I worked in the founder's office on AI tooling and email automation, so that "
    "kind of work is familiar to me.\n\n"
    "I would like to be considered for the Founder's Office Intern role from November 2026 "
    "to April 2027. I have attached my resume for your reference. Would you be open to "
    "considering me for this role?\n\n"
    "Best regards,\nDaksh Jain\nBCA, Christ University, Bengaluru\ndakshjainn02@gmail.com"
)


def draft(**overrides):
    return {
        "lead_id": "opp_1",
        "to": "admin@auraaison.com",
        "to_source": "https://www.linkedin.com/posts/auraaisonn_x",
        "subject": "Founder's Office Internship Application - Daksh Jain",
        "body": BODY,
        "attachment": "Daksh-Jain-founders_office.pdf",
        "listing_subject": None,
        **overrides,
    }


def test_clean_draft_passes() -> None:
    assert check_email_draft(draft()) == []


def test_word_count_bounds() -> None:
    assert any(e.startswith("body_too_short") for e in check_email_draft(draft(body="Too short to send.")))
    assert any(e.startswith("body_too_long") for e in check_email_draft(draft(body=BODY + " " + BODY)))


def test_formal_greeting_and_signature_required() -> None:
    no_greeting = BODY.replace("Dear Auraaison team,\n\n", "")
    assert "missing_greeting" in check_email_draft(draft(body=no_greeting))
    no_signature = BODY.split("Best regards,")[0] + "Thanks"
    assert "missing_signature" in check_email_draft(draft(body=no_signature + " and more words " * 3))


def test_subject_rules_and_listing_override() -> None:
    assert any(e.startswith("subject_word_count") for e in check_email_draft(draft(subject="hi")))
    assert "subject_missing_internship" in check_email_draft(draft(subject="A quick note for your team"))
    assert "subject_fake_reply_prefix" in check_email_draft(draft(subject="Re: Founder's Office Internship"))
    # The listing's own subject wins over the generic subject rules.
    required = draft(subject="Founder's Office", listing_subject="Founder's Office")
    assert check_email_draft(required) == []
    assert "subject_ignores_listing_instruction" in check_email_draft(
        draft(listing_subject="Founder's Office")
    )


def test_humanizer_checks_are_reused() -> None:
    errors = check_email_draft(draft(body=BODY.replace("That line", "That line — honestly")))
    assert "punctuation:em-dash" in errors
    errors = check_email_draft(draft(body=BODY + " I want to leverage this."))
    assert "forbidden_word:leverage" in errors


def test_unverified_metrics_and_links_are_blocked() -> None:
    assert "unverified_metric" in check_email_draft(draft(body=BODY.replace("email automation", "email automation that lifted replies 35%")))
    assert "unverified_metric" in check_email_draft(draft(body=BODY.replace("email automation", "email automation for 200+ leads a week")))
    two_links = BODY + " https://a.example and https://b.example"
    assert "too_many_links:2" in check_email_draft(draft(body=two_links))


def test_attachment_must_be_a_known_resume() -> None:
    assert "attachment_not_allowed" in check_email_draft(draft(attachment="portfolio.zip"))


def test_recipient_needs_a_source_and_null_is_allowed() -> None:
    assert "recipient_missing_source" in check_email_draft(draft(to_source=""))
    assert "recipient_invalid" in check_email_draft(draft(to="founder at auraaison"))
    assert check_email_draft(draft(to=None, to_source="")) == []
    assert check_email_draft(draft(to_source="entered_by_daksh")) == []


def test_cli_reports_errors_and_exit_code(tmp_path: Path) -> None:
    path = tmp_path / "drafts.json"
    path.write_text(json.dumps([draft(), draft(lead_id="opp_2", subject="Hi")], ensure_ascii=False), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "execution" / "check_draft.py"
    result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["opp_1"] == []
    assert report["opp_2"]
