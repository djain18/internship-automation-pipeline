from __future__ import annotations

import json
import os
from typing import Any

from models import Record, clean_text, fold_text, grounded_in
from research import cached_bedrock_json


MAX_REASON_CHARS = 180
# Fallback only; the real cap is config/scoring.yml:max_linkedin_extractions_per_run.
LINKEDIN_EXTRACTION_LIMIT = 10
# Per-call batch size. Kept small enough that one call's output (~350 tokens
# per resolved record) stays well inside max_tokens=3500 — a 2026-09-11 live
# run truncated a 20x6000-char batch mid-JSON and failed closed.
# 2026-09-13: 10 was still too big. run_f9ae04eb99b98d0e lost 3 of 10 batches
# to `Unterminated string` at char ~11970 (≈3500 output tokens exactly), i.e.
# 10 records x 300-char quote sits right on the ceiling. 5 halves it.
LINKEDIN_EXTRACTION_BATCH_SIZE = 5
# The location words a post must state for the role to be in scope. One
# definition shared by the extraction candidate filter and the validator so
# the two can never drift apart.
LOCATION_TERMS = ("bengaluru", "bangalore", "remote", "hybrid")


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


def _verdict_error(item: Any) -> str:
    """Empty when one ranked row is well-formed; otherwise why it is not.
    Bounds an over-long reason in place."""
    if not isinstance(item, dict):
        return "each ranked item must be an object"
    score = item.get("fit_score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        return "fit_score must be an integer from 0 to 100"
    if not isinstance(item.get("relevant"), bool) or not isinstance(item.get("spam"), bool):
        return "relevant and spam must be booleans"
    reason = clean_text(item.get("reason"))
    if not reason:
        return "reason must not be empty"
    if len(reason) > MAX_REASON_CHARS:
        reason = reason[: MAX_REASON_CHARS - 3].rstrip() + "..."
    item["reason"] = reason
    return ""


def _validate_response(payload: Any, expected_ids: set[str]) -> list[Record]:
    """Strict whole-response check. Used by eval_models.py, where a model that
    cannot return a clean shortlist should fail its evaluation."""
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
        error = _verdict_error(item)
        if error:
            raise ValueError(error)
    return ranked


def _usable_verdicts(payload: Any, expected_ids: set[str]) -> dict[str, Record]:
    """Every well-formed verdict for a supplied id, first occurrence wins.

    Production scoring no longer rejects the whole section for one bad row:
    run_8df9363eaeef875d (2026-09-14) lost all 22 leads and the day's digest
    to a single ID mismatch. Unknown, duplicate and malformed rows are dropped;
    a lead with no usable verdict fails closed on its own in score_shortlist.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("ranked"), list):
        raise ValueError("response must contain a ranked list")
    verdicts: dict[str, Record] = {}
    for item in payload["ranked"]:
        identifier = clean_text(item.get("id")) if isinstance(item, dict) else ""
        if identifier in expected_ids and identifier not in verdicts and not _verdict_error(item):
            verdicts[identifier] = item
    if not verdicts:
        raise ValueError("response contained no usable verdict for the supplied shortlist")
    return verdicts


def _extraction_batch_content(candidates: list[Record]) -> dict[str, Any]:
    return {
        "instruction": (
            "Extract only explicitly stated hiring fields. Return raw JSON as "
            '{"records":[{"id":"...","company":"","title":"","location":"",'
            '"apply_url":"","evidence_quote":""}]}. Include every ID exactly once. '
            "company, title and location must each be copied verbatim from the post; do not "
            "normalise, expand or abbreviate them. They do not have to sit near each other -- "
            "the employer is usually named in the opening line and the role details hundreds of "
            "characters later. evidence_quote must be an exact substring of the post, no longer "
            "than 300 characters, that proves the internship role. "
            "Leave a field empty when the post does not state it."
        ),
        "records": [
            # 3000 chars: the 2026-09-11 live run truncated a 20x6000 batch
            # mid-JSON and failed closed. Hiring facts sit in the first lines.
            {"id": item["id"], "text": str(item.get("description", ""))[:3000]}
            for item in candidates
        ],
    }


def _apply_extraction_result(record: Record, result: dict[str, Any] | None) -> tuple[Record, bool]:
    item = dict(record)
    if result is None:
        return item, False
    text = str(record.get("description", ""))
    post = fold_text(text)
    quote = clean_text(result.get("evidence_quote"))
    company = clean_text(result.get("company"))
    title = clean_text(result.get("title"))
    location = clean_text(result.get("location"))
    # Every field is grounded against the WHOLE post, not one shared 300-char
    # window. Requiring employer + role + location inside a single quote made
    # a normally-written hiring post unresolvable: Auraaison's Founder's Office
    # Intern post says "We're hiring at Auraaison." at char 0 and
    # "Role: Founder's Office Intern Location: Bengaluru / Remote" at char ~880.
    # No 300-char substring can hold both, so the model had to return either an
    # empty field or a quote missing the company, and either failed closed.
    # Across five consecutive live runs that rejected 67-84 of every 100 paid
    # posts (resolved 16/28/31/27/33), including the single best-fit Bengaluru
    # Founder's Office internship in the pool. Adjacency was never evidence;
    # each claim being a verbatim substring of the real post is.
    stated_terms = [term for term in LOCATION_TERMS if term in fold_text(location)]
    valid = bool(
        grounded_in(quote, post)
        and grounded_in(company, post)
        and "intern" in fold_text(title)
        and grounded_in(title, post)
        and stated_terms
        and any(term in post for term in stated_terms)
    )
    if not valid:
        return item, False
    item.update(
        {
            "company": company,
            "title": title,
            "location": location,
            "extraction_evidence_quote": quote,
            "extraction_status": "llm_evidence_validated",
        }
    )
    apply_url = clean_text(result.get("apply_url"))
    if apply_url and apply_url in text:
        item["apply_url"] = apply_url
    return item, True


def extract_linkedin_hiring_fields(
    records: list[Record],
    cache: dict[str, Any] | None = None,
    scoring: dict[str, Any] | None = None,
) -> tuple[list[Record], Record]:
    """Resolve structured fields for every qualifying LinkedIn post, in
    bounded batches, and reject unquoted output.

    Previously capped at a hardcoded 10 posts total. On 2026-09-12, 76 of 99
    identity-missing posts qualified but only 10 were attempted, silently
    dropping same-day exact-match roles. The cap now comes from
    config/scoring.yml (max_linkedin_extractions_per_run) and candidates are
    split into LINKEDIN_EXTRACTION_BATCH_SIZE-sized calls so one oversized
    prompt cannot truncate and lose the tail.
    """

    scoring = scoring or {}
    run_limit = int(scoring.get("max_linkedin_extractions_per_run", LINKEDIN_EXTRACTION_LIMIT))
    all_candidates = [
        item
        for item in records
        if item.get("source") == "linkedin_posts_apify"
        and not all(item.get(key) for key in ("company", "title", "location"))
        and "intern" in str(item.get("description", "")).casefold()
        and any(
            term in str(item.get("description", "")).casefold()
            for term in ("hiring", "opening", "apply")
        )
        and any(
            term in str(item.get("description", "")).casefold()
            for term in LOCATION_TERMS
        )
    ]
    candidates = all_candidates[:run_limit]
    if not candidates:
        return records, {"status": "not_needed", "candidates": len(all_candidates), "sent": 0, "resolved": 0}
    if os.getenv("ENABLE_BEDROCK", "").casefold() not in {"1", "true", "yes"}:
        return records, {
            "status": "skipped_disabled",
            "candidates": len(all_candidates),
            "sent": 0,
            "resolved": 0,
        }
    model_id = os.getenv("BEDROCK_RESEARCH_MODEL_ID", "")
    region = os.getenv("AWS_REGION", "")
    if not model_id or not region:
        return records, {
            "status": "skipped_missing_configuration",
            "candidates": len(all_candidates),
            "sent": 0,
            "resolved": 0,
        }

    resolved_by_id: dict[str, dict[str, Any]] = {}
    attempted = 0
    usages: list[dict[str, Any]] = []
    errors: list[str] = []
    for start in range(0, len(candidates), LINKEDIN_EXTRACTION_BATCH_SIZE):
        batch = candidates[start : start + LINKEDIN_EXTRACTION_BATCH_SIZE]
        content = _extraction_batch_content(batch)
        prompt = json.dumps(content, ensure_ascii=False)
        try:
            payload, usage = cached_bedrock_json(
                purpose="linkedin_hiring_field_extraction",
                model_id=model_id,
                prompt_version="v1",
                content=content,
                prompt=prompt,
                region=region,
                cache=cache,
                # 2026-09-13: halving the batch to 5 did NOT stop the
                # `Unterminated string` truncations (run_21ae706418041f9a still
                # lost 3 of 22 batches at ~13k output chars) because the model
                # sometimes ignores the 300-char evidence_quote instruction and
                # echoes the whole 3000-char post back. 5 x 3000 chars of echo
                # needs ~6000 tokens of headroom. Unused ceiling costs nothing:
                # billing is on tokens actually emitted.
                max_tokens=6000,
            )
            extracted = payload.get("records") if isinstance(payload, dict) else None
            if not isinstance(extracted, list):
                raise ValueError("response must contain a records list")
            supplied_ids = {str(item["id"]) for item in batch}
            # Keep only IDs we actually sent. A stray or duplicated ID used to
            # raise and discard the whole batch (3 of 10 batches on
            # run_f9ae04eb99b98d0e), even though every surviving record still
            # has to clear _apply_extraction_result's exact-quote validator
            # before anything is written. Drop the bad rows, keep the good.
            by_id: dict[str, Any] = {}
            for item in extracted:
                if not isinstance(item, dict):
                    continue
                identifier = str(item.get("id"))
                if identifier in supplied_ids:
                    by_id.setdefault(identifier, item)
            if not by_id:
                raise ValueError("extraction returned no IDs from the supplied records")
        except Exception as exc:
            # One bad batch doesn't sink the rest: it is left unresolved
            # (still rejected downstream by hard_exclusions) while later
            # batches still get their own attempt.
            errors.append(f"{type(exc).__name__}: {str(exc)[:240]}")
            attempted += len(batch)
            continue
        attempted += len(batch)
        resolved_by_id.update(by_id)
        usages.append(usage)

    candidate_ids = {str(item["id"]) for item in candidates}
    output: list[Record] = []
    resolved = 0
    for record in records:
        result = resolved_by_id.get(str(record.get("id")))
        if str(record.get("id")) not in candidate_ids:
            output.append(dict(record))
            continue
        item, was_resolved = _apply_extraction_result(record, result)
        resolved += int(was_resolved)
        output.append(item)

    combined_usage = {
        "calls": sum(int(u.get("calls", 1)) for u in usages),
        "cache_hits": sum(int(u.get("cache_hits", 0)) for u in usages),
        "input_tokens": sum(int(u.get("input_tokens", 0)) for u in usages),
        "output_tokens": sum(int(u.get("output_tokens", 0)) for u in usages),
        "total_tokens": sum(int(u.get("total_tokens", 0)) for u in usages),
        "elapsed_ms": sum(int(u.get("elapsed_ms", 0)) for u in usages),
        "cost_usd": sum(float(u.get("cost_usd", 0) or 0) for u in usages),
    }
    return output, {
        "status": "ok" if not errors else ("failed" if not usages else "partial"),
        "candidates": len(all_candidates),
        "sent": attempted,
        "resolved": resolved,
        "usage": combined_usage,
        "error": "; ".join(errors)[:500] if errors else "",
    }


def score_shortlist(
    records: list[Record],
    scoring: dict[str, Any],
    section: str,
    cache: dict[str, Any] | None = None,
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
    # The model sees 1..N, never the real ids. run_8df9363eaeef875d
    # (2026-09-14) sent 22 records keyed by 20-char hex ids and Kimi's reply
    # failed the exact-ID check, cancelling that day's digest. Short aliases
    # remove the copying error; code maps them back below.
    alias_to_id = {str(index): record["id"] for index, record in enumerate(records, 1)}
    supplied = []
    for alias, record in zip(alias_to_id, records):
        research = record.get("research") or {}
        supplied.append(
            {
                "id": alias,
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
    content = {
            "instruction": (
                "Score these already deterministically eligible internship leads for "
                "Daksh Jain's Founder’s Office/generalist target. Reward real founder "
                "exposure, right-hand-to-founder/CEO scope, 0-to-1 end-to-end "
                "ownership across GTM, fundraising, operations, or product, "
                "business, operations, growth, "
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
        }
    prompt = json.dumps(
        content,
        ensure_ascii=False,
    )
    verdicts: dict[str, Record] = {}
    usages: list[Record] = []
    error = ""
    attempts = 0
    # One retry when the reply is unusable or incomplete (temperature 0.1, so a
    # second read of the same prompt can differ). The better attempt wins.
    for attempts in (1, 2):
        attempt_usage: Record | None = None
        try:
            payload, attempt_usage = cached_bedrock_json(
                purpose=f"shortlist_rank:{section}",
                model_id=model_id,
                prompt_version="v1",
                content=content,
                prompt=prompt,
                region=region,
                cache=cache,
                # 2026-09-13: the 1800-token default was set for a shortlist of
                # 10; at llm_shortlist_size:30, ~30 x (rank, fit_score,
                # relevant, spam, 180-char reason) sits right on that limit.
                # Sized for 40 records with headroom.
                max_tokens=5000,
            )
            attempt_verdicts = _usable_verdicts(payload, set(alias_to_id))
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:240]}"
            attempt_verdicts = {}
        if attempt_usage is not None:
            usages.append(attempt_usage)
        if len(attempt_verdicts) > len(verdicts):
            verdicts = attempt_verdicts
        if len(verdicts) == len(alias_to_id):
            break
        if cache is not None and attempt_usage is not None:
            # Never pin a failed or partial answer: the retry and any later run
            # with the same shortlist must ask the model again.
            cache.pop(str(attempt_usage.get("cache_key", "")), None)
    if not verdicts:
        return _failed(records, "failed", error), {
            "status": "failed",
            "section": section,
            "model_id": model_id,
            "attempts": attempts,
            "error": error,
        }
    usage: Record = {
        **usages[-1],
        **{
            key: sum(u.get(key, 0) or 0 for u in usages)
            for key in (
                "calls", "cache_hits", "input_tokens", "output_tokens",
                "total_tokens", "elapsed_ms", "cost_usd",
            )
        },
    }
    missing_aliases = [alias for alias in alias_to_id if alias not in verdicts]

    def model_order(alias: str) -> tuple[int, int]:
        rank = verdicts[alias].get("rank")
        valid_rank = isinstance(rank, int) and not isinstance(rank, bool)
        return (rank if valid_rank else len(alias_to_id) + 1, int(alias))

    # Ranks are renumbered 1..k in the model's order, so a gap or tie in its
    # ranks never costs a verdict.
    new_rank = {alias: rank for rank, alias in enumerate(sorted(verdicts, key=model_order), 1)}
    threshold = int(scoring.get("llm_fit_threshold", 70))
    missing = {alias_to_id[alias] for alias in missing_aliases}
    output: list[Record] = _failed(
        [record for record in records if record["id"] in missing],
        "missing_from_response",
        "model returned no usable verdict for this lead",
    )
    for alias, record in zip(alias_to_id, records):
        if alias not in verdicts:
            continue
        verdict = verdicts[alias]
        item = dict(record)
        relevant = bool(verdict["relevant"])
        spam = bool(verdict["spam"])
        fit_score = int(verdict["fit_score"])
        item.update(
            {
                "llm_rank": new_rank[alias],
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
    # Scored leads by rank first, then unscored ones in their original order.
    output.sort(key=lambda item: item["llm_rank"] or len(alias_to_id) + 1)
    return output, {
        "status": "partial" if missing_aliases else "ok",
        "section": section,
        "model_id": model_id,
        "usage": usage,
        "admitted": sum(bool(item["digest_approved"]) for item in output),
        "withheld": sum(not bool(item["digest_approved"]) for item in output),
        "missing": len(missing_aliases),
        "attempts": attempts,
    }



ROLE_JUDGEMENT_INSTRUCTION = (
    "Daksh Jain wants a Founder's Office or generalist internship: broad, "
    "cross-functional ownership across business, operations, growth or strategy, "
    "with real founder or leadership exposure: right-hand to the founder/CEO, "
    "0-to-1 end-to-end execution, GTM, fundraising, or ops with no fixed "
    "single-track scope. Each record below already passed "
    "every other filter and failed only a keyword test for cross-functional "
    "scope. Read the description, not the title. Answer cross_functional true "
    "when the described work genuinely spans more than one business function, "
    "explicitly involves working directly with founders or leadership on "
    "varied projects, OR -- treat this as an equally strong positive signal, "
    "not a weaker one -- when the role has NO fixed job description at all: "
    "the founder or team hands the intern ad hoc problems to solve as they "
    "come up, the work is open-ended ('wear many hats', 'figure it out', "
    "'own whatever needs doing', 'build what the team needs', 'interact with "
    "customers and build', 'comfortable with ambiguity', 'trusted generalist', "
    "'whatever it takes', 'direct founder access', 'junior chief of staff' -- "
    "real phrases founders actually use when hiring for this exact role), or "
    "the posting is deliberately vague about scope because the role itself is "
    "meant to flex across whatever the business "
    "needs that week. A THIN description is not evidence against fit here -- "
    "an intentionally open-ended, no-fixed-JD role often reads thin because "
    "there is nothing fixed to describe, and that is exactly the shape Daksh "
    "wants. Answer false only when the description affirmatively describes a "
    "SINGLE-TRACK specialist role with a fixed, narrow scope (engineering, "
    "design, finance, legal, pure sales quota carrying, content-only) and "
    "gives no sign of broader ownership. When genuinely ambiguous between a "
    "narrow specialist role and an open-ended generalist one, prefer true. "
    "Never invent detail that is not in the text. Return ONLY raw JSON as "
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
    model_id = os.getenv("BEDROCK_RESEARCH_MODEL_ID", "")
    candidate_keys: dict[str, str] = {}
    from models import llm_cache_key

    for record in candidates:
        content = {
            "title": record.get("title"),
            "company": record.get("company"),
            "description": str(record.get("description", ""))[:6000],
        }
        key, _ = llm_cache_key(
            "role_judgement", model_id, "v1", content
        )
        candidate_keys[record["id"]] = key
        entry = cache.get(key)
        verdict = entry.get("verdict") if isinstance(entry, dict) else None
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
    region = os.getenv("AWS_REGION", "")
    usage: Any = None
    if not considered:
        status = "cache_only" if cached_hits else "not_needed"
    elif os.getenv("ENABLE_BEDROCK", "").casefold() not in {"1", "true", "yes"}:
        status = "skipped_disabled"
    elif not model_id or not region:
        status = "skipped_missing_configuration"
    else:
        content = {
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
            }
        prompt = json.dumps(
            content,
            ensure_ascii=False,
        )
        try:
            call_cache: dict[str, Any] = {}
            payload, usage = cached_bedrock_json(
                purpose="role_judgement_batch",
                model_id=model_id,
                prompt_version="v1",
                content=content,
                prompt=prompt,
                region=region,
                cache=call_cache,
            )
            verdicts = _validate_judgements(
                payload, {record["id"] for record in considered}
            )
            for identifier, verdict in verdicts.items():
                cache[candidate_keys[identifier]] = {
                    "purpose": "role_judgement",
                    "model_id": model_id,
                    "prompt_version": "v1",
                    "verdict": verdict,
                }
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
        entry = cache.get(candidate_keys.get(identifier, "")) or {}
        record["role_fit_reason"] = clean_text(
            (entry.get("verdict") or {}).get("reason")
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
        "usage": usage or {
            "calls": 0,
            "cache_hits": cached_hits,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "elapsed_ms": 0,
            "cost_usd": 0.0,
        },
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
