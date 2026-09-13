from outreach import choose_strategy, draft_outreach, validate_outreach


def test_outreach_is_short_human_and_never_send_ready() -> None:
    record = {
        "company": "Nebula AI",
        "title": "Founder Office Intern",  # Use plain ascii
        "location": "Bengaluru",
        "source_url": "https://example.com/job",
        "selected_contact": {"name": "Aarav"},
        "research": {
            "solution_concept": "an evidence-led workflow audit with a human approval gate.",
            "observed_problem_signal": "The listing asks for cross-functional ownership.",
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
    # No more pre-written email body -- a paste-ready Claude Code prompt
    # takes its place. Daksh drafts the real email himself with /humanizer.
    assert "claude_prompt" in draft
    assert "Nebula AI" in draft["claude_prompt"]
    assert "/humanizer" in draft["claude_prompt"]
    assert [item["day"] for item in draft["followups"]] == [3, 8, 14]
    assert draft["followups"][0]["status"] == "suppressed_no_new_cited_value"
    assert draft["followups"][1]["status"] == "suppressed_no_new_cited_value"


def test_artifact_mention_allowed_requires_human_approval() -> None:
    base = {
        "company": "Nebula AI", "title": "Operations Intern", "location": "Bengaluru",
        "research": {"solution_concept": "an operations workflow audit."},
        "artifact_path": "artifacts/audit.md",
    }
    blocked = draft_outreach(base)
    approved = draft_outreach({**base, "artifact_human_approved": True})
    assert not blocked["artifact_mention_allowed"]
    assert approved["artifact_mention_allowed"]


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
    """Tone checks still run on whatever Daksh's own prose remains --
    the LinkedIn note/message -- now that the email body is gone."""
    draft = {
        "email_subject": "founder office idea",
        "linkedin_note": "I hope this email finds you well.",
        "linkedin_message": "Short note",
        "send_status": "draft_needs_human_review",
    }
    assert any(error.startswith("forbidden_phrase") for error in validate_outreach(draft))


def test_validator_blocks_em_dash() -> None:
    """Drafts with em dashes fail validation."""
    draft = {
        "email_subject": "founder office idea",
        "linkedin_note": "This is interesting—something I found.",
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("em-dash" in err for err in errors)


def test_validator_blocks_emoji() -> None:
    """Drafts with emoji fail validation, not only the hand-listed smileys."""
    for emoji in ("😊", "🚀", "✨", "✅", "⚡"):
        draft = {
            "email_subject": "founder office idea",
            "linkedin_note": f"Great opportunity {emoji} check this out.",
            "send_status": "draft_needs_human_review",
        }
        assert "punctuation:emoji" in validate_outreach(draft), emoji


def test_validator_blocks_forbidden_word_delve() -> None:
    """Drafts with 'delve' fail validation."""
    draft = {
        "email_subject": "founder office idea",
        "linkedin_note": "I want to delve into this opportunity.",
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("delve" in err for err in errors)


def test_validator_blocks_linkedin_note_over_300_chars() -> None:
    """LinkedIn connection notes over 300 characters fail validation."""
    draft = {
        "email_subject": "founder office idea",
        "linkedin_note": "x" * 301,
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("linkedin_note_too_long" in err for err in errors)


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
    assert draft["claude_prompt"]
    assert "messy content workflow" in draft["claude_prompt"]


def test_outreach_produces_a_prompt_and_two_linkedin_artifacts() -> None:
    """Outreach produces a Claude Code prompt, connection note, and message."""
    record = {
        "company": "Test Corp",
        "title": "Founder's Office Intern",
        "location": "Bengaluru",
        "source_url": "https://example.com/job",
        "selected_contact": {"name": "Test"},
        "research": {
            "solution_concept": "a workflow audit.",
            "observed_problem_signal": "The listing asks for broad ownership.",
        },
    }
    draft = draft_outreach(record)
    assert "claude_prompt" in draft
    assert draft["claude_prompt"]
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


def test_claude_prompt_carries_the_real_observed_signal() -> None:
    """The prompt must ground Claude Code in the actual quote, not a
    paraphrase -- so a company's own word choice ("robust") is expected to
    appear verbatim, the same way it always was evidence, not AI tone."""
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
    assert "robust enterprise agents" in draft["claude_prompt"]
    assert validate_outreach(draft) == []


def test_claude_prompt_never_double_quotes_a_signal_that_already_quotes_itself() -> None:
    """deterministic_research's own observation reads 'The listing states:
    "..."' -- wrapping that again in quotes nested them and read as broken,
    exactly the AI-slop look this feature exists to avoid."""
    record = {
        "company": "Acme", "title": "Intern", "source_url": "https://acme.com/job",
        "research": {
            "solution_concept": "a workflow audit.",
            "observed_problem_signal": 'The listing states: "You will own weekly revenue reporting."',
        },
    }
    draft = draft_outreach(record)
    assert '""' not in draft["claude_prompt"]
    assert 'The listing states: "You will own weekly revenue reporting."' in draft["claude_prompt"]


def test_claude_prompt_never_generated_without_a_real_signal() -> None:
    """A prompt built on nothing real would hand Claude Code a blank canvas
    to invent facts on -- exactly what this pipeline exists to prevent. The
    draft is blocked, not silently marked ready with an empty prompt."""
    record = {
        "company": "No Evidence Co",
        "selected_contact": {"name": "Someone"},
        "research": {"solution_concept": "a workflow audit."},  # no observed_problem_signal
    }
    draft = draft_outreach(record)
    assert draft["claude_prompt"] == ""
    assert draft["send_status"] == "blocked_no_evidence"
    assert validate_outreach(draft) == []


def test_validator_still_catches_a_three_item_list_in_the_linkedin_prose() -> None:
    """The structural checks pointed at email_subject once the email body was
    removed, which made them unfireable -- a 2-4 word subject can never hold a
    bulleted list. They must run on the prose Daksh actually sends."""
    draft = {
        "email_subject": "founder office idea",
        "linkedin_message": (
            "Thanks for connecting. I mapped three things:\n"
            "- First thing\n"
            "- Second thing\n"
            "- Third thing\n"
        ),
        "linkedin_note": "Short note",
        "send_status": "draft_needs_human_review",
    }
    errors = validate_outreach(draft)
    assert any("three_item_list" in error for error in errors)


def test_malformed_email_template_falls_back_instead_of_crashing_the_run(
    tmp_path, monkeypatch
) -> None:
    """templates/email_prompt.txt is hand-editable; one stray brace used to
    raise straight out of draft_outreach, which run_pipeline calls in an
    unguarded loop -- a text-file typo would have taken down the whole run."""
    import outreach

    monkeypatch.setattr(
        outreach,
        "load_prompt_template",
        lambda *_a, **_k: "# {company_name}\n\nA stray {brace} nobody supplies.",
    )
    record = {
        "company": "Acme",
        "title": "Intern",
        "source_url": "https://acme.com/job",
        "research": {
            "solution_concept": "a workflow audit.",
            "observed_problem_signal": "The listing asks for broad ownership.",
        },
    }
    draft = draft_outreach(record)
    assert draft["send_status"] == "draft_needs_human_review"
    assert "Acme" in draft["claude_prompt"]
    assert "/humanizer" in draft["claude_prompt"]
