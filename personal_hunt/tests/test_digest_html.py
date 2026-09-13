from email import message_from_bytes
import base64

import digest


def _run():
    item = {
        "id": "opp-1",
        "company": "Example <Labs>",
        "title": "Founder’s Office Intern",
        "location": "Bengaluru",
        "score": 88,
        "llm_fit_score": 92,
        "resume": "Daksh-Jain-founders_office",
        "source_url": "https://example.com/source?a=1&b=2",
        "apply_url": "https://example.com/apply",
    }
    return {
        "run_date": "2026-09-10",
        "digest_primary": [item],
        "digest_remote_fallback": [],
        "primary": [item],
        "remote_fallback": [],
        "funding_primary": [],
        "funding_extended": [],
        "source_health": [],
        "daily_target": 10,
        "daily_min_target": 5,
    }


def test_rise_html_digest_escapes_source_data():
    rendered = digest.render_html_digest(_run())
    assert "Rise" in rendered
    assert "Example &lt;Labs&gt;" in rendered
    assert "Example <Labs>" not in rendered
    assert "Open my hunt" in rendered


def test_send_self_digest_builds_multipart_message(monkeypatch):
    captured = {}

    class Execute:
        def execute(self):
            return {"id": "gmail-1"}

    class Messages:
        def send(self, **kwargs):
            captured.update(kwargs)
            return Execute()

    class Users:
        def messages(self):
            return Messages()

    class Service:
        def users(self):
            return Users()

    monkeypatch.setenv(
        "GMAIL_TOKEN_JSON",
        '{"token":"x","refresh_token":"r","token_uri":"https://oauth2.googleapis.com/token","client_id":"c","client_secret":"s"}',
    )
    monkeypatch.setenv("GMAIL_DIGEST_TO", "dakshinjain187@gmail.com")
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *_args, **_kwargs: Service())
    message_id = digest.send_self_digest("Subject", "Plain", "<b>HTML</b>")
    assert message_id == "gmail-1"
    parsed = message_from_bytes(base64.urlsafe_b64decode(captured["body"]["raw"]))
    assert parsed.is_multipart()
    assert {part.get_content_type() for part in parsed.walk()} >= {"text/plain", "text/html"}



def test_html_digest_shows_contact_and_prompt_link_on_a_match() -> None:
    run = _run()
    run["digest_primary"][0]["selected_contact"] = {"email": "admin@example.com", "confidence": "medium"}
    run["digest_primary"][0]["outreach"] = {"claude_prompt": "# prompt"}
    html_body = digest.render_html_digest(run)
    assert "admin@example.com" in html_body
    assert "Copy Claude Code prompt" in html_body


def test_html_digest_empty_day_explains_itself_instead_of_an_empty_table() -> None:
    run = _run()
    run["digest_primary"] = []
    run["primary"] = [{"id": "x", "digest_approved": False}]
    run["eligible_count"] = 3
    html_body = digest.render_html_digest(run)
    assert "<table" not in html_body
    assert "3 passed the filters and 1 was withheld" in html_body


def test_html_digest_surfaces_failed_sources_spotted_leads_and_staleness() -> None:
    run = _run()
    run["source_health"] = [{"source_id": "yc_bengaluru", "status": "failed"}, {"source_id": "wwr", "status": "ok"}]
    run["spotted_leads"] = [{"source_url": "https://www.linkedin.com/posts/x"}]
    run["staleness_warning"] = "Latest artifact is 2 days old."
    html_body = digest.render_html_digest(run)
    assert "Sources that failed this run: yc_bengaluru" in html_body
    assert "wwr" not in html_body
    assert "https://www.linkedin.com/posts/x" in html_body
    assert "Latest artifact is 2 days old." in html_body
