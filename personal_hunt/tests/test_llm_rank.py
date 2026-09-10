import llm_rank


def test_kimi_fit_and_spam_gate(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setenv("BEDROCK_RESEARCH_MODEL_ID", "moonshotai.kimi-k2.5")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setattr(
        llm_rank,
        "_bedrock_json_with_usage",
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
        "_bedrock_json_with_usage",
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
        "_bedrock_json_with_usage",
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


def test_judge_cross_functional_admits_from_cache_without_calling_the_model() -> None:
    from llm_rank import judge_cross_functional

    records = [_cross_functional_record("a", ["role_not_cross_functional"])]
    cache = {"a": {"cross_functional": True, "reason": "spans ops and hiring"}}
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
