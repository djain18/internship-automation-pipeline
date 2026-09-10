from eval_models import evaluate_rank_case, evaluate_text


def test_model_eval_detects_required_and_forbidden_content() -> None:
    passed = evaluate_text(
        "This is public evidence; the severity must be verified.",
        ["public", "verified"],
        ["guaranteed"],
    )
    failed = evaluate_text(
        "This is guaranteed to increase revenue.",
        ["public"],
        ["guaranteed"],
    )
    assert passed["passed"]
    assert not failed["passed"]


def test_rank_eval_requires_expected_spam_relevance_and_threshold() -> None:
    response = {
        "ranked": [
            {
                "id": "spam",
                "rank": 1,
                "fit_score": 5,
                "relevant": False,
                "spam": True,
                "reason": "Promotional course, not a real opening.",
            }
        ]
    }
    result = evaluate_rank_case(
        response,
        {
            "records": [{"id": "spam"}],
            "expected": [
                {"id": "spam", "admitted": False, "relevant": False, "spam": True}
            ],
        },
    )
    assert result["passed"]

