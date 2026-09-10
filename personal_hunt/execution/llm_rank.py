from __future__ import annotations

import json
import os
from typing import Any

from models import Record, clean_text
from research import _bedrock_json_with_usage


MAX_REASON_CHARS = 180


def _failed(records: list[Record], status: str, error: str = "") -> list[Record]:
    output: list[Record] = []
    for record in records:
        item = dict(record)
        item.update(
            {
                "llm_rank": None,
                "llm_fit_score": None,
                "llm_relevant": False,
                "llm_spam": False,
                "llm_rank_reason": "",
                "llm_rank_status": status,
                "llm_rank_error": error[:300],
                "digest_approved": False,
            }
        )
        output.append(item)
    return output


def _validate_response(payload: Any, expected_ids: set[str]) -> list[Record]:
    if not isinstance(payload, dict) or not isinstance(payload.get("ranked"), list):
        raise ValueError("response must contain a ranked list")
    ranked = payload["ranked"]
    ids = [clean_text(item.get("id")) for item in ranked if isinstance(item, dict)]
    if len(ids) != len(ranked) or set(ids) != expected_ids or len(ids) != len(expected_ids):
        raise ValueError("response IDs must match the supplied shortlist exactly")
    ranks = [item.get("rank") for item in ranked]
    if sorted(ranks) != list(range(1, len(ranked) + 1)):
        raise ValueError("ranks must be unique consecutive integers")
    for item in ranked:
        score = item.get("fit_score")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise ValueError("fit_score must be an integer from 0 to 100")
        if not isinstance(item.get("relevant"), bool) or not isinstance(
            item.get("spam"), bool
        ):
            raise ValueError("relevant and spam must be booleans")
        reason = clean_text(item.get("reason"))
        if not reason:
            raise ValueError("reason must not be empty")
        if len(reason) > MAX_REASON_CHARS:
            item["reason"] = reason[: MAX_REASON_CHARS - 3].rstrip() + "..."
        else:
            item["reason"] = reason
    return ranked


def score_shortlist(
    records: list[Record], scoring: dict[str, Any], section: str
) -> tuple[list[Record], Record]:
    if not records:
        return [], {"status": "not_needed", "section": section}
    if os.getenv("ENABLE_BEDROCK", "").casefold() not in {"1", "true", "yes"}:
        return _failed(records, "skipped_disabled"), {
            "status": "skipped_disabled",
            "section": section,
        }
    model_id = os.getenv("BEDROCK_RESEARCH_MODEL_ID", "")
    region = os.getenv("AWS_REGION", "")
    if not model_id or not region:
        return _failed(records, "skipped_missing_configuration"), {
            "status": "skipped_missing_configuration",
            "section": section,
        }
    supplied = []
    for record in records:
        research = record.get("research") or {}
        supplied.append(
            {
                "id": record["id"],
                "company": record.get("company"),
                "title": record.get("title"),
                "location_class": record.get("location_class"),
                "lane": record.get("lane"),
                "deterministic_score": record.get("score"),
                "score_components": record.get("score_components"),
                "score_reasons": record.get("score_reasons"),
                "source_confidence": record.get("source_confidence"),
                "verification_status": record.get("verification_status"),
                "posted_date": record.get("posted_date"),
                "posted_date_basis": record.get("posted_date_basis"),
                "description": str(record.get("description", ""))[:6000],
                "evidence": research.get("evidence", []),
            }
        )
    prompt = json.dumps(
        {
            "instruction": (
                "Score these already deterministically eligible internship leads for "
                "Daksh Jain's Founder’s Office/generalist target. Reward real founder "
                "exposure, cross-functional ownership, business, operations, growth, "
                "strategy breadth, Bengaluru or supported India-remote fit, and evidence "
                "quality. Mark spam when promotional, scraped noise, a course/training "
                "pitch, deceptive, duplicated content, not a real opening, or missing "
                "enough evidence of an internship. Mark irrelevant when primarily "
                "specialist engineering, design, finance, or sales without broad "
                "generalist ownership. Missing evidence lowers fit_score. Never invent "
                "facts. Return ONLY raw JSON as "
                "{\"ranked\":[{\"id\":\"...\",\"rank\":1,\"fit_score\":0," 
                "\"relevant\":false,\"spam\":false,\"reason\":\"...\"}]}. "
                "Include every ID exactly once, consecutive ranks, integer scores 0-100, "
                "and grounded reasons no longer than 180 characters."
            ),
            "section": section,
            "records": supplied,
        },
        ensure_ascii=False,
    )
    try:
        payload, usage = _bedrock_json_with_usage(prompt, model_id, region)
        ranked = _validate_response(payload, {record["id"] for record in records})
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:240]}"
        return _failed(records, "failed", error), {
            "status": "failed",
            "section": section,
            "model_id": model_id,
            "error": error,
        }
    by_id = {item["id"]: item for item in ranked}
    threshold = int(scoring.get("llm_fit_threshold", 70))
    output: list[Record] = []
    for record in records:
        verdict = by_id[record["id"]]
        item = dict(record)
        relevant = bool(verdict["relevant"])
        spam = bool(verdict["spam"])
        fit_score = int(verdict["fit_score"])
        item.update(
            {
                "llm_rank": int(verdict["rank"]),
                "llm_fit_score": fit_score,
                "llm_relevant": relevant,
                "llm_spam": spam,
                "llm_rank_reason": clean_text(verdict["reason"]),
                "llm_rank_status": "ok",
                "llm_rank_error": "",
                "digest_approved": fit_score >= threshold and relevant and not spam,
            }
        )
        output.append(item)
    output.sort(key=lambda item: (int(item["llm_rank"]), item["id"]))
    return output, {
        "status": "ok",
        "section": section,
        "model_id": model_id,
        "usage": usage,
        "admitted": sum(bool(item["digest_approved"]) for item in output),
        "withheld": sum(not bool(item["digest_approved"]) for item in output),
    }



ROLE_JUDGEMENT_INSTRUCTION = (
    "Daksh Jain wants a Founder's Office or generalist internship: broad, "
    "cross-functional ownership across business, operations, growth or strategy, "
    "with real founder or leadership exposure. Each record below already passed "
    "every other filter and failed only a keyword test for cross-functional "
    "scope. Read the description, not the title. Answer cross_functional true "
    "ONLY when the described work genuinely spans more than one business "
    "function or explicitly involves working directly with founders or "
    "leadership on varied projects. Answer false for a single-track specialist "
    "role (engineering, design, finance, legal, pure sales quota carrying, "
    "content only), and false when the description is too thin to tell. Never "
    "invent detail that is not in the text. Return ONLY raw JSON as "
    '{"judgements":[{"id":"...","cross_functional":false,"reason":"..."}]}, '
    "one entry per supplied ID, reasons no longer than 180 characters."
)


def _judgement_candidates(records: list[Record]) -> list[Record]:
    """Records rejected for the cross-functional keyword test and nothing else."""
    return [
        record
        for record in records
        if list(record.get("rejection_reasons") or []) == ["role_not_cross_functional"]
    ]


def judge_cross_functional(
    records: list[Record],
    scoring: dict[str, Any],
    cache: dict[str, Any] | None = None,
) -> tuple[list[Record], Record, dict[str, Any]]:
    """Tier 2 of the role test: a bounded yes/no read of the description.

    Only records that fail the cross-functional keyword test and nothing else are
    considered, the number sent per run is capped, verdicts are cached by record
    id, and every failure path leaves the record rejected (fails closed).
    """
    cache = dict(cache or {})
    candidates = _judgement_candidates(records)
    if not candidates:
        return records, {"status": "not_needed", "candidates": 0}, cache

    output = {record["id"]: record for record in records}
    admitted_ids: list[str] = []
    cached_hits = 0
    pending: list[Record] = []
    for record in candidates:
        verdict = cache.get(record["id"])
        if isinstance(verdict, dict) and "cross_functional" in verdict:
            cached_hits += 1
            if verdict.get("cross_functional"):
                admitted_ids.append(record["id"])
        else:
            pending.append(record)

    cap = int(scoring.get("max_role_judgements_per_run", 25))
    considered = pending[:cap]
    skipped_over_cap = len(pending) - len(considered)

    status = "ok"
    error = ""
    model_id = os.getenv("BEDROCK_RESEARCH_MODEL_ID", "")
    region = os.getenv("AWS_REGION", "")
    usage: Any = None
    if not considered:
        status = "cache_only" if cached_hits else "not_needed"
    elif os.getenv("ENABLE_BEDROCK", "").casefold() not in {"1", "true", "yes"}:
        status = "skipped_disabled"
    elif not model_id or not region:
        status = "skipped_missing_configuration"
    else:
        prompt = json.dumps(
            {
                "instruction": ROLE_JUDGEMENT_INSTRUCTION,
                "records": [
                    {
                        "id": record["id"],
                        "title": record.get("title"),
                        "company": record.get("company"),
                        "description": str(record.get("description", ""))[:6000],
                    }
                    for record in considered
                ],
            },
            ensure_ascii=False,
        )
        try:
            payload, usage = _bedrock_json_with_usage(prompt, model_id, region)
            verdicts = _validate_judgements(
                payload, {record["id"] for record in considered}
            )
            for identifier, verdict in verdicts.items():
                cache[identifier] = verdict
                if verdict["cross_functional"]:
                    admitted_ids.append(identifier)
        except Exception as exc:  # fails closed: nothing is admitted
            status = "failed"
            error = f"{type(exc).__name__}: {str(exc)[:240]}"

    for identifier in admitted_ids:
        record = dict(output[identifier])
        record["rejection_reasons"] = []
        record["eligible"] = True
        record["role_fit_basis"] = "llm_cross_functional_judgement"
        record["role_fit_reason"] = clean_text(
            (cache.get(identifier) or {}).get("reason")
        )
        output[identifier] = record

    meta: Record = {
        "status": status,
        "candidates": len(candidates),
        "cached": cached_hits,
        "sent": len(considered) if status in {"ok", "failed"} else 0,
        "skipped_over_cap": skipped_over_cap,
        "admitted": len(admitted_ids),
        "model_id": model_id,
    }
    if error:
        meta["error"] = error
    return [output[record["id"]] for record in records], meta, cache


def _validate_judgements(
    payload: Any, expected_ids: set[str]
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("judgements"), list):
        raise ValueError("response must contain a judgements list")
    verdicts: dict[str, dict[str, Any]] = {}
    for item in payload["judgements"]:
        if not isinstance(item, dict):
            raise ValueError("each judgement must be an object")
        identifier = clean_text(item.get("id"))
        if identifier not in expected_ids or identifier in verdicts:
            raise ValueError("judgement IDs must match the supplied records exactly")
        if not isinstance(item.get("cross_functional"), bool):
            raise ValueError("cross_functional must be a boolean")
        reason = clean_text(item.get("reason"))
        verdicts[identifier] = {
            "cross_functional": item["cross_functional"],
            "reason": reason[:MAX_REASON_CHARS],
        }
    if set(verdicts) != expected_ids:
        raise ValueError("judgement IDs must match the supplied records exactly")
    return verdicts
