from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from config import AUTOMATION_ROOT
from llm_rank import _validate_response
from research import _bedrock_json_with_usage


def evaluate_text(text: str, required: list[str], forbidden: list[str]) -> dict[str, object]:
    lowered = text.casefold()
    required_hits = {term: term.casefold() in lowered for term in required}
    forbidden_hits = {term: term.casefold() in lowered for term in forbidden}
    passed = all(required_hits.values()) and not any(forbidden_hits.values())
    return {
        "passed": passed,
        "required_hits": required_hits,
        "forbidden_hits": forbidden_hits,
    }


def evaluate_rank_case(response: dict[str, object], case: dict[str, object]) -> dict[str, object]:
    records = case.get("records", [])
    expected_ids = {str(item["id"]) for item in records if isinstance(item, dict)}
    ranked = _validate_response(response, expected_ids)
    by_id = {str(item["id"]): item for item in ranked}
    checks: dict[str, bool] = {}
    for expected in case.get("expected", []):
        identifier = str(expected["id"])
        verdict = by_id[identifier]
        passed = True
        if "admitted" in expected:
            admitted = (
                int(verdict["fit_score"]) >= 70
                and verdict["relevant"] is True
                and verdict["spam"] is False
            )
            passed = passed and admitted is bool(expected["admitted"])
        if "spam" in expected:
            passed = passed and verdict["spam"] is bool(expected["spam"])
        if "relevant" in expected:
            passed = passed and verdict["relevant"] is bool(expected["relevant"])
        checks[identifier] = passed
    return {"passed": all(checks.values()), "verdict_checks": checks}


def _rank_prompt(case: dict[str, object]) -> str:
    return json.dumps(
        {
            "instruction": (
                "Score these internship leads for Daksh Jain's Founder’s Office or "
                "generalist target. Mark spam for promotional, deceptive, course or "
                "training pitches, scraped noise, or content that is not a real opening. "
                "Mark irrelevant for specialist-only work without broad ownership. "
                "Return ONLY raw JSON as {\"ranked\":[{\"id\":\"...\",\"rank\":1," 
                "\"fit_score\":0,\"relevant\":false,\"spam\":false," 
                "\"reason\":\"...\"}]}. Include every ID exactly once, integer "
                "scores 0-100, consecutive ranks, and reasons under 180 characters."
            ),
            "records": case.get("records", []),
        },
        ensure_ascii=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a Bedrock research model")
    parser.add_argument(
        "--cases",
        type=Path,
        default=AUTOMATION_ROOT / "fixtures" / "model-eval.json",
    )
    parser.add_argument("--model-id", default=os.getenv("BEDROCK_RESEARCH_MODEL_ID", ""))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", ""))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.model_id or not args.region:
        raise RuntimeError("BEDROCK_RESEARCH_MODEL_ID and AWS_REGION are required")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    results = []
    for case in cases:
        task = case.get("task", "research")
        prompt = (
            _rank_prompt(case)
            if task == "rank"
            else json.dumps(
                {
                "instruction": (
                    "Use only the supplied evidence. Respond with ONLY a raw JSON "
                    "object with observed_problem_signal, inference, why_it_matters, "
                    "solution_concept, uncertainty. No markdown fences, no preamble, "
                    "no commentary outside the JSON. Explicitly say what is public "
                    "evidence and what must be verified."
                ),
                "case": case,
                },
                ensure_ascii=False,
            )
        )
        try:
            response, usage = _bedrock_json_with_usage(prompt, args.model_id, args.region)
        except Exception as exc:
            results.append(
                {
                    "id": case["id"],
                    "response": {"error": f"{type(exc).__name__}: {str(exc)[:200]}"},
                    "passed": False,
                    "required_hits": {},
                    "forbidden_hits": {},
                    "task": task,
                    "must_reject": bool(case.get("must_reject")),
                }
            )
            continue
        if task == "rank":
            try:
                grade = evaluate_rank_case(response, case)
            except Exception as exc:
                grade = {"passed": False, "validation_error": str(exc)[:300]}
        else:
            rendered = json.dumps(response, ensure_ascii=False)
            grade = evaluate_text(
                rendered,
                case.get("required_terms", []),
                case.get("forbidden_terms", []),
            )
        results.append(
            {
                "id": case["id"],
                "task": task,
                "must_reject": bool(case.get("must_reject")),
                "response": response,
                "usage": usage,
                **grade,
            }
        )
    pass_rate = sum(bool(item["passed"]) for item in results) / max(len(results), 1)
    must_reject_passed = all(
        bool(item["passed"]) for item in results if item.get("must_reject")
    )
    report = {
        "model_id": args.model_id,
        "region": args.region,
        "case_count": len(results),
        "pass_rate": pass_rate,
        "must_reject_passed": must_reject_passed,
        "accepted": pass_rate >= 0.90 and must_reject_passed,
        "results": results,
    }
    output = args.output or (
        AUTOMATION_ROOT / "out" / f"model-eval-{args.model_id.replace('/', '-')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), **report}, ensure_ascii=False, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

