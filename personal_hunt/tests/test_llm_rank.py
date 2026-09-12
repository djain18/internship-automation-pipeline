import llm_rank


def test_role_judgement_instruction_treats_no_fixed_jd_as_positive() -> None:
    """Regression for Daksh's explicit 2026-09-13 clarification: a founder's
    office role often has no fixed JD by nature (the founder hands out ad hoc
    problems), and that must read as a POSITIVE signal for cross_functional,
    not as "too thin to tell" -- which is what the instruction used to say."""
    instruction = llm_rank.ROLE_JUDGEMENT_INSTRUCTION.casefold()
    assert "too thin to tell" not in instruction
    assert "no fixed job description" in instruction
    assert "thin description is not evidence against fit" in instruction


def test_kimi_fit_and_spam_gate(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda *_args, **_kwargs: (
            {
                "ranked": [
                    {
                        "id": "good",
                        "rank": 1,
                        "fit_score": 91,
                        "relevant": True,
                        "spam": False,
                        "reason": "Broad founder-facing ownership is explicit.",
                    },
                    {
                        "id": "spam",
                        "rank": 2,
                        "fit_score": 10,
                        "relevant": False,
                        "spam": True,
                        "reason": "This is a promotional training pitch, not a role.",
                    },
                ]
            },
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        ),
    )
    records = [
        {"id": "good", "company": "GoodCo", "title": "Founder’s Office Intern"},
        {"id": "spam", "company": "SpamCo", "title": "Campus training internship"},
    ]
    scored, summary = llm_rank.score_shortlist(records, {"llm_fit_threshold": 70}, "primary")
    by_id = {item["id"]: item for item in scored}
    assert by_id["good"]["digest_approved"]
    assert not by_id["spam"]["digest_approved"]
    assert summary["admitted"] == 1


def test_invalid_kimi_batch_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda *_args, **_kwargs: ({"ranked": []}, {}),
    )
    scored, summary = llm_rank.score_shortlist(
        [{"id": "candidate", "company": "Co", "title": "Generalist Intern"}],
        {"llm_fit_threshold": 70},
        "primary",
    )
    assert not scored[0]["digest_approved"]
    assert summary["status"] == "failed"


def test_overlong_reason_is_bounded_without_discarding_valid_verdict(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda *_args, **_kwargs: (
            {
                "ranked": [
                    {
                        "id": "candidate",
                        "rank": 1,
                        "fit_score": 90,
                        "relevant": True,
                        "spam": False,
                        "reason": "Grounded fit evidence. " * 20,
                    }
                ]
            },
            {},
        ),
    )

    scored, summary = llm_rank.score_shortlist(
        [{"id": "candidate", "company": "Co", "title": "Generalist Intern"}],
        {"llm_fit_threshold": 70},
        "primary",
    )

    assert summary["status"] == "ok"
    assert scored[0]["digest_approved"]
    assert len(scored[0]["llm_rank_reason"]) == 180
    assert scored[0]["llm_rank_reason"].endswith("...")



def _cross_functional_record(identifier: str, reasons: list[str]) -> dict:
    return {
        "id": identifier,
        "company": "SeedCo",
        "title": "Marketing Intern",
        "description": "Own campaigns, hiring and vendor operations with the founder.",
        "rejection_reasons": list(reasons),
        "eligible": not reasons,
    }


def test_judge_cross_functional_only_considers_sole_reason_records() -> None:
    from llm_rank import judge_cross_functional

    records = [
        _cross_functional_record("a", ["role_not_cross_functional", "senior_role"]),
        _cross_functional_record("b", []),
    ]
    output, meta, cache = judge_cross_functional(records, {}, {})
    assert meta["status"] == "not_needed"
    assert meta["candidates"] == 0
    assert cache == {}
    assert output == records


def test_judge_cross_functional_fails_closed_when_disabled(monkeypatch) -> None:
    from llm_rank import judge_cross_functional

    monkeypatch.delenv("ENABLE_BEDROCK", raising=False)
    records = [_cross_functional_record("a", ["role_not_cross_functional"])]
    output, meta, _ = judge_cross_functional(records, {}, {})
    assert meta["status"] == "skipped_disabled"
    assert meta["admitted"] == 0
    assert output[0]["rejection_reasons"] == ["role_not_cross_functional"]


def test_judge_cross_functional_admits_from_cache_without_calling_the_model(monkeypatch) -> None:
    from llm_rank import judge_cross_functional
    from models import llm_cache_key

    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    records = [_cross_functional_record("a", ["role_not_cross_functional"])]
    key, _ = llm_cache_key(
        "role_judgement",
        "model-a",
        "v1",
        {
            "title": "Marketing Intern",
            "company": "SeedCo",
            "description": "Own campaigns, hiring and vendor operations with the founder.",
        },
    )
    cache = {
        key: {
            "verdict": {"cross_functional": True, "reason": "spans ops and hiring"}
        }
    }
    output, meta, _ = judge_cross_functional(records, {}, cache)
    assert meta["status"] == "cache_only"
    assert meta["cached"] == 1
    assert output[0]["eligible"] is True
    assert output[0]["rejection_reasons"] == []
    assert output[0]["role_fit_basis"] == "llm_cross_functional_judgement"


def test_judge_cross_functional_caps_records_per_run(monkeypatch) -> None:
    from llm_rank import judge_cross_functional

    monkeypatch.delenv("ENABLE_BEDROCK", raising=False)
    records = [
        _cross_functional_record(str(index), ["role_not_cross_functional"])
        for index in range(30)
    ]
    _, meta, _ = judge_cross_functional(records, {"max_role_judgements_per_run": 5}, {})
    assert meta["candidates"] == 30
    assert meta["skipped_over_cap"] == 25


def test_llm_judged_record_earns_cross_functional_role_breadth() -> None:
    """Otherwise a Tier 2 admission dies at publish_threshold and is decorative."""
    from datetime import date

    from config import load_all
    from score import score_record

    config = load_all()
    record = {
        "title": "Marketing Intern",
        "description": "Own campaigns, community and vendor operations.",
        "location_class": "bengaluru_onsite",
        "eligible": True,
        "rejection_reasons": [],
        "role_fit_basis": "llm_cross_functional_judgement",
        "source_confidence": "medium",
    }
    scored = score_record(record, config["roles"], config["scoring"], date(2026, 9, 8))
    assert scored["score_components"]["role_breadth"] == 14
    assert "role:llm_cross_functional_judgement" in scored["score_reasons"]


def test_shortlist_cache_skips_identical_call_and_invalidates_content(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    calls = 0

    def fake_cached(**kwargs):
        nonlocal calls
        from models import llm_cache_key

        key, content_hash = llm_cache_key(
            kwargs["purpose"], kwargs["model_id"], kwargs["prompt_version"], kwargs["content"]
        )
        if key in kwargs["cache"]:
            return kwargs["cache"][key]["payload"], {
                "calls": 0, "cache_hits": 1, "cache_key": key,
                "content_hash": content_hash,
            }
        calls += 1
        payload = {"ranked": [{
            "id": "candidate", "rank": 1, "fit_score": 90,
            "relevant": True, "spam": False, "reason": "grounded",
        }]}
        kwargs["cache"][key] = {"payload": payload}
        return payload, {"calls": 1, "cache_hits": 0, "cache_key": key,
                         "content_hash": content_hash}

    monkeypatch.setattr(llm_rank, "cached_bedrock_json", fake_cached)
    cache = {}
    record = {"id": "candidate", "company": "Co", "title": "Generalist Intern"}
    _, first = llm_rank.score_shortlist([record], {}, "primary", cache)
    _, second = llm_rank.score_shortlist([record], {}, "primary", cache)
    changed = {**record, "description": "Changed scope"}
    llm_rank.score_shortlist([changed], {}, "primary", cache)
    assert calls == 2
    assert first["usage"]["calls"] == 1
    assert second["usage"]["cache_hits"] == 1


def test_linkedin_batch_extraction_requires_exact_evidence_quote(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    text = "Signal AI is hiring a Growth Intern in Bengaluru. Apply at https://signal.ai/jobs/1"
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda **_kwargs: (
            {
                "records": [
                    {
                        "id": "post-1",
                        "company": "Signal AI",
                        "title": "Growth Intern",
                        "location": "Bengaluru",
                        "apply_url": "https://signal.ai/jobs/1",
                        "evidence_quote": text,
                    }
                ]
            },
            {"calls": 1, "cache_hits": 0, "total_tokens": 20},
        ),
    )
    records = [
        {
            "id": "post-1",
            "source": "linkedin_posts_apify",
            "company": "",
            "title": "",
            "location": "",
            "description": text,
            "source_url": "https://linkedin.com/posts/1",
        }
    ]
    output, meta = llm_rank.extract_linkedin_hiring_fields(records, {})
    assert meta["resolved"] == 1
    assert output[0]["company"] == "Signal AI"
    assert output[0]["apply_url"] == "https://signal.ai/jobs/1"


def test_linkedin_batch_extraction_rejects_unquoted_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    text = "Hiring an intern for a remote role."
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda **_kwargs: (
            {
                "records": [
                    {
                        "id": "post-1",
                        "company": "Invented Co",
                        "title": "Growth Intern",
                        "location": "Bengaluru",
                        "apply_url": "",
                        "evidence_quote": "Invented Co is hiring in Bengaluru",
                    }
                ]
            },
            {"calls": 1},
        ),
    )
    records = [
        {
            "id": "post-1",
            "source": "linkedin_posts_apify",
            "description": text,
        }
    ]
    output, meta = llm_rank.extract_linkedin_hiring_fields(records, {})
    assert meta["resolved"] == 0
    assert not output[0].get("company")


def _linkedin_candidate(index: int) -> dict:
    text = f"Company{index} is hiring a Growth Intern in Bengaluru. Apply now."
    return {
        "id": f"post-{index}",
        "source": "linkedin_posts_apify",
        "company": "",
        "title": "",
        "location": "",
        "description": text,
        "source_url": f"https://linkedin.com/posts/{index}",
    }


def test_linkedin_extraction_cap_comes_from_scoring_config_not_hardcoded_ten(monkeypatch) -> None:
    # 2026-09-12 incident: 76 of 99 identity-missing posts qualified for
    # extraction but a hardcoded limit of 10 attempted only 10, dropping a
    # same-day exact-match Founder's Office post purely for want of a parse.
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    calls: list[list[str]] = []

    def fake_cached(**kwargs):
        ids = [item["id"] for item in kwargs["content"]["records"]]
        calls.append(ids)
        return (
            {
                "records": [
                    {
                        "id": identifier,
                        "company": f"Company{identifier.split('-')[1]}",
                        "title": "Growth Intern",
                        "location": "Bengaluru",
                        "apply_url": "",
                        "evidence_quote": f"Company{identifier.split('-')[1]} is hiring a Growth Intern in Bengaluru.",
                    }
                    for identifier in ids
                ]
            },
            {"calls": 1, "total_tokens": 20},
        )

    monkeypatch.setattr(llm_rank, "cached_bedrock_json", fake_cached)
    records = [_linkedin_candidate(index) for index in range(25)]

    output, meta = llm_rank.extract_linkedin_hiring_fields(
        records, {}, scoring={"max_linkedin_extractions_per_run": 25}
    )

    assert meta["candidates"] == 25
    assert meta["sent"] == 25
    assert meta["resolved"] == 25
    # 25 candidates / 5-per-batch => 5 calls, not 1 oversized call.
    assert len(calls) == 5
    assert sum(len(batch) for batch in calls) == 25
    assert all(item.get("company") for item in output)


def test_linkedin_extraction_reports_skipped_over_cap(monkeypatch) -> None:
    # Explicitly disabled (rather than relying on an unset env var, which a
    # local .env with ENABLE_BEDROCK=true would otherwise override) so this
    # stays a fast, no-network unit test.
    monkeypatch.setenv("ENABLE_BEDROCK", "false")
    records = [_linkedin_candidate(index) for index in range(15)]
    _, meta = llm_rank.extract_linkedin_hiring_fields(
        records, {}, scoring={"max_linkedin_extractions_per_run": 5}
    )
    # candidates must reflect every post the predicate matched, not just the
    # capped subset, so a caller can tell the cap is binding.
    assert meta["candidates"] == 15
    assert meta["status"] == "skipped_disabled"


def test_linkedin_batch_extraction_accepts_clean_subset(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    text = "Signal AI is hiring a Growth Intern in Bengaluru. Apply at https://signal.ai/jobs/1"
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda **_kwargs: (
            {
                "records": [
                    {
                        "id": "post-1",
                        "company": "Signal AI",
                        "title": "Growth Intern",
                        "location": "Bengaluru",
                        "apply_url": "https://signal.ai/jobs/1",
                        "evidence_quote": text,
                    }
                ]
            },
            {"calls": 1},
        ),
    )
    records = [
        {
            "id": "post-1",
            "source": "linkedin_posts_apify",
            "company": "",
            "title": "",
            "location": "",
            "description": text,
            "source_url": "https://linkedin.com/posts/1",
        },
        {
            "id": "post-2",
            "source": "linkedin_posts_apify",
            "company": "",
            "title": "",
            "location": "",
            "description": "Hiring an intern for a hybrid role, apply inside.",
            "source_url": "https://linkedin.com/posts/2",
        },
    ]
    output, meta = llm_rank.extract_linkedin_hiring_fields(records, {})
    assert meta["status"] == "ok"
    assert meta["resolved"] == 1
    assert output[0]["company"] == "Signal AI"
    assert not output[1].get("company")


def test_linkedin_batch_extraction_keeps_good_rows_when_model_returns_stray_id(
    monkeypatch,
) -> None:
    # run_f9ae04eb99b98d0e lost 3 of 10 batches to "extraction IDs must be a
    # clean subset of supplied records": one hallucinated or duplicated id
    # discarded every other record in the same call. Stray rows are dropped;
    # the rest still go through the exact-quote validator.
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    text = "Signal AI is hiring a Growth Intern in Bengaluru. Apply now."
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda **_kwargs: (
            {
                "records": [
                    {
                        "id": "post-not-sent",
                        "company": "Ghost Co",
                        "title": "Growth Intern",
                        "location": "Bengaluru",
                        "evidence_quote": "Ghost Co is hiring a Growth Intern in Bengaluru.",
                    },
                    {
                        "id": "post-1",
                        "company": "Signal AI",
                        "title": "Growth Intern",
                        "location": "Bengaluru",
                        "evidence_quote": text,
                    },
                ]
            },
            {"calls": 1},
        ),
    )
    records = [
        {
            "id": "post-1",
            "source": "linkedin_posts_apify",
            "company": "",
            "title": "",
            "location": "",
            "description": text,
            "source_url": "https://linkedin.com/posts/1",
        }
    ]
    output, meta = llm_rank.extract_linkedin_hiring_fields(records, {})
    assert meta["status"] == "ok"
    assert meta["resolved"] == 1
    assert output[0]["company"] == "Signal AI"
    assert not any(item.get("company") == "Ghost Co" for item in output)


def test_linkedin_batch_extraction_fails_batch_when_no_supplied_id_returned(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "model-a")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setattr(
        llm_rank,
        "cached_bedrock_json",
        lambda **_kwargs: ({"records": [{"id": "nope", "company": "Ghost Co"}]}, {"calls": 1}),
    )
    records = [
        {
            "id": "post-1",
            "source": "linkedin_posts_apify",
            "company": "",
            "title": "",
            "location": "",
            "description": "Signal AI is hiring a Growth Intern in Bengaluru. Apply now.",
            "source_url": "https://linkedin.com/posts/1",
        }
    ]
    output, meta = llm_rank.extract_linkedin_hiring_fields(records, {})
    assert meta["status"] == "failed"
    assert meta["resolved"] == 0
    assert not output[0].get("company")
