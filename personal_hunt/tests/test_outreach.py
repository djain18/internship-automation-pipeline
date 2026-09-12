from outreach import choose_strategy, draft_outreach, validate_outreach


def test_outreach_is_short_human_and_never_send_ready() -> None:
    record = {
        "company": "Nebula AI",
        "title": "Founder Office Intern",  # Use plain ascii
        "location": "Bengaluru",
        "selected_contact": {"name": "Aarav"},
        "research": {
            "solution_concept": "an evidence-led workflow audit with a human approval gate.",
            "uncertainty": "the internal workflow has not been confirmed.",
        },
        "artifact_status": "generated_unverified",
    }
    draft = draft_outreach(record)
    # The generic path is what every internship match uses; it has to satisfy
    # its own validator, not merely produce keys.
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
        "email_subject": "founder office idea",
        "email_body": "I hope this email finds you well. " + "useful " * 85,
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    assert any(error.startswith("forbidden_phrase") for error in validate_outreach(draft))


def test_validator_blocks_em_dash() -> None:
    """Drafts with em dashes fail validation."""
    draft = {
        "email_subject": "founder office idea",
        "email_body": "This is interesting—something I found. " + "content " * 20,
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("em-dash" in err for err in errors)


def test_validator_blocks_emoji() -> None:
    """Drafts with emoji fail validation, not only the hand-listed smileys."""
    for emoji in ("😊", "🚀", "✨", "✅", "⚡"):
        draft = {
            "email_subject": "founder office idea",
            "email_body": f"Great opportunity {emoji} check this out. " + "content " * 20,
            "linkedin_note": "Short note",
            "send_status": "draft_needs_human_review",
        }
        assert "punctuation:emoji" in validate_outreach(draft), emoji


def test_validator_catches_inline_header_bullets() -> None:
    """The bullet-header check runs on the raw body, which keeps its newlines."""
    draft = {
        "email_subject": "founder office idea",
        "email_body": "Some intro text here.\n- Scope: one prototype\nClosing line.",
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    assert "inline_header_bullets" in validate_outreach(draft)


def test_validator_blocks_forbidden_word_delve() -> None:
    """Drafts with 'delve' fail validation."""
    draft = {
        "email_subject": "founder office idea",
        "email_body": "I want to delve into this opportunity. " + "content " * 20,
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("delve" in err for err in errors)


def test_validator_blocks_linkedin_note_over_300_chars() -> None:
    """LinkedIn connection notes over 300 characters fail validation."""
    draft = {
        "email_subject": "founder office idea",
        "email_body": "This is a test. " * 10,
        "linkedin_note": "x" * 301,
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("linkedin_note_too_long" in err for err in errors)


def test_validator_blocks_three_item_list() -> None:
    """Drafts with three-item lists fail validation."""
    draft = {
        "email_subject": "founder office idea",
        # Need 80-110 words. Include numbered list that should fail
        "email_body": ("I have been researching your company and found a great opportunity for the role. "
                       "I understand the work involves strategic planning and operations oversight. "
                       "Here is my detailed approach for managing the responsibilities effectively. "
                       "I can support the team across several important dimensions.\n"
                       "1. First thing - primary focus area\n"
                       "2. Second thing - secondary area\n"
                       "3. Third thing - additional area\n"
                       "I believe this structured approach will help the team succeed."),
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("three_item_list" in err for err in errors), f"Expected three_item_list error, got: {errors}"


def test_problem_led_company_gets_problem_led_outreach() -> None:
    """Companies with deep_problem_research and prompt_generation use problem-led drafting."""
    record = {
        "company": "Nebula AI",
        "selected_contact": {"name": "Aarav"},
        "deep_problem_research": {
            "observed_signals": [
                {"text": "The company has a messy content workflow.", "url": "https://example.com"}
            ],
            "problem_hypothesis": "Manual content operations at scale is slowing delivery.",
        },
        "prompt_generation": {
            "prompt_text": "Build a content router prototype...",
            "artifact_path": "artifacts/router.md",
        },
    }
    draft = draft_outreach(record)
    assert draft["send_status"] == "draft_needs_human_review"
    assert draft["draft_source"] == "problem_led"
    assert "prototype" in draft["email_body"].casefold()
    assert draft["email_body"]  # Should have content


def test_outreach_produces_three_artifacts() -> None:
    """Outreach produces email, connection note, and message."""
    record = {
        "company": "Test Corp",
        "title": "Founder's Office Intern",
        "location": "Bengaluru",
        "selected_contact": {"name": "Test"},
        "research": {"solution_concept": "a workflow audit."},
    }
    draft = draft_outreach(record)
    assert "email_body" in draft
    assert "email_subject" in draft
    assert "linkedin_note" in draft
    assert "linkedin_message" in draft
    assert len(draft["linkedin_note"]) <= 300
    assert "thanks" in draft["linkedin_message"].casefold()


def test_linkedin_note_never_truncates_mid_sentence() -> None:
    """A long company/title must shorten the note, not slice it mid-word."""
    record = {
        "company": "Bharat Agritech and Rural Supply Chain Technologies Private Limited",
        "title": "Founder Office and Strategic Operations Generalist Intern (Bengaluru, Hybrid)",
        "location": "Bengaluru",
        "selected_contact": {"name": "Aarav"},
        "research": {"solution_concept": "a workflow audit."},
    }
    note = draft_outreach(record)["linkedin_note"]
    assert len(note) <= 300
    assert note.rstrip()[-1] in ".?!"


def test_quoted_evidence_does_not_trip_forbidden_words() -> None:
    """A company's own word choice inside a quote is evidence, not AI tone."""
    record = {
        "company": "Lyzr AI",
        "selected_contact": {"name": "Aarav"},
        "deep_problem_research": {
            "observed_signals": [
                {"text": "We build robust enterprise agents for regulated buyers.", "url": "https://lyzr.ai"}
            ],
            "problem_hypothesis": "Delivery load sits with solution consultants.",
        },
        "prompt_generation": {"prompt_text": "Build a delivery-load tracker."},
    }
    draft = draft_outreach(record)
    assert "robust" in draft["email_body"]
    assert validate_outreach(draft) == []


def test_daksh_own_prose_still_fails_on_forbidden_word() -> None:
    """The quoted-span carve-out must not disable the check everywhere."""
    draft = {
        "email_subject": "founder office idea",
        "email_body": "I want to leverage this. " + "content " * 20,
        "linkedin_note": "Short note",
        "quoted_span": "We build enterprise agents",
        "send_status": "draft_needs_human_review",
    }
    assert any("leverage" in error for error in validate_outreach(draft))

