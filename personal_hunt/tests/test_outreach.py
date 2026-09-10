from outreach import draft_outreach, validate_outreach


def test_outreach_is_short_human_and_never_send_ready() -> None:
    record = {
        "company": "Nebula AI",
        "title": "Founder’s Office Intern",
        "location": "Bengaluru",
        "selected_contact": {"name": "Aarav"},
        "research": {
            "solution_concept": "an evidence-led workflow audit with a human approval gate.",
            "uncertainty": "the internal workflow has not been confirmed.",
        },
        "artifact_status": "generated_unverified",
    }
    draft = draft_outreach(record)
    assert validate_outreach(draft) == []
    assert draft["send_status"] == "draft_needs_human_review"
    assert not draft["artifact_mention_allowed"]
    assert [item["day"] for item in draft["followups"]] == [3, 8, 14]


def test_validator_blocks_fake_marketing_phrase() -> None:
    draft = {
        "subject": "founder office idea",
        "email_body": "I hope this email finds you well. " + "useful " * 85,
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    assert any(error.startswith("forbidden_phrase") for error in validate_outreach(draft))


