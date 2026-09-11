from outreach import choose_strategy, draft_outreach, validate_outreach


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
    assert draft["followups"][0]["status"] == "suppressed_no_new_cited_value"
    assert draft["followups"][1]["status"] == "suppressed_no_new_cited_value"


def test_artifact_is_mentioned_only_when_real_and_human_approved() -> None:
    base = {
        "company": "Nebula AI", "title": "Operations Intern", "location": "Bengaluru",
        "research": {"solution_concept": "an operations workflow audit."},
        "artifact_path": "artifacts/audit.md",
    }
    blocked = draft_outreach(base)
    approved = draft_outreach({**base, "artifact_human_approved": True})
    assert not blocked["artifact_mention_allowed"]
    assert "artifacts/audit.md" not in blocked["email_body"]
    assert approved["artifact_mention_allowed"]
    assert "artifacts/audit.md" in approved["email_body"]


def test_strategy_and_followups_are_evidence_derived() -> None:
    record = {
        "company": "Nebula AI", "title": "Growth Intern",
        "research": {
            "solution_concept": "a growth funnel teardown.",
            "followup_evidence": [{
                "day": 3, "observation": "The company published a new onboarding flow.",
                "source_url": "https://example.com/update", "access_date": "2026-09-11",
                "confidence": "high",
            }],
        },
    }
    draft = draft_outreach(record)
    assert choose_strategy(record) == "growth_funnel_teardown"
    assert draft["strategy_id"] == "growth_funnel_teardown"
    assert draft["followups"][0]["status"] == "draft_needs_human_review"
    assert draft["followups"][1]["status"] == "suppressed_no_new_cited_value"


def test_validator_blocks_fake_marketing_phrase() -> None:
    draft = {
        "subject": "founder office idea",
        "email_body": "I hope this email finds you well. " + "useful " * 85,
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    assert any(error.startswith("forbidden_phrase") for error in validate_outreach(draft))

