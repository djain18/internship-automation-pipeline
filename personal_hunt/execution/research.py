from __future__ import annotations

import json
import os
from company_site import fetch_site_evidence, primary_responsibility
from models import Record, canonical_url, clean_text
from firecrawl_research import maybe_add_firecrawl_evidence


def evidence_ledger(record: Record) -> list[Record]:
    ledger: list[Record] = []
    if record.get("source_url"):
        ledger.append(
            {
                "type": "opportunity",
                "title": record.get("title"),
                "url": record.get("source_url"),
                "date": record.get("discovered_at"),
                "observation": (
                    f"{record.get('company')} published or was listed for "
                    f"{record.get('title')}."
                ),
                "confidence": record.get("source_confidence", "medium"),
            }
        )
    for item in record.get("evidence") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        if any(existing["url"] == item.get("url") for existing in ledger):
            if item.get("observation"):
                ledger[0]["observation"] = clean_text(item.get("observation"))
            continue
        ledger.append(
            {
                "type": clean_text(item.get("type") or "source"),
                "title": clean_text(item.get("title") or item.get("url")),
                "url": clean_text(item.get("url")),
                "date": clean_text(item.get("date") or record.get("discovered_at")),
                "observation": clean_text(item.get("observation")),
                "confidence": clean_text(item.get("confidence") or "medium"),
            }
        )
    if record.get("funding_source_url") and not any(
        item["url"] == record["funding_source_url"] for item in ledger
    ):
        ledger.append(
            {
                "type": "funding",
                "title": "Funding or growth source",
                "url": record.get("funding_source_url"),
                "date": record.get("funding_date") or record.get("discovered_at"),
                "observation": clean_text(record.get("growth_signal") or "Funding signal"),
                "confidence": "medium",
            }
        )
    return ledger


def deterministic_research(record: Record) -> Record:
    ledger = evidence_ledger(record)
    role = clean_text(record.get("title"))
    company = clean_text(record.get("company"))
    observation = (
        ledger[0]["observation"] if ledger and ledger[0]["observation"]
        else f"A public listing associates {company} with the {role} opportunity."
    )
    # What the company wrote it needs someone to own IS the operational gap. A
    # solution built on the listing's own sentence is grounded; the lane-keyed
    # strings this replaced were the same three lines on every record.
    responsibility = primary_responsibility(record.get("description", ""))
    if responsibility:
        observation = f'The listing states: "{responsibility}"'
        solution = (
            "a one-page operating map of that work: decisions, inputs, owners, "
            "handoffs, and the step most ready for a small automation."
        )
        solution_basis = "job_description"
    else:
        solution = ""
        solution_basis = "insufficient_evidence"
    return {
        "status": "provisional" if ledger else "research_pending",
        "evidence": ledger,
        "evidence_confidence": "high" if len(ledger) >= 2 else "medium" if ledger else "low",
        "observed_problem_signal": observation,
        "inference": (
            f"The breadth of {role} may create a need for clearer cross-functional "
            "priorities and lightweight operating systems."
        ),
        "why_it_matters": (
            "Small founder-led teams lose speed when ownership, evidence, and recurring "
            "handoffs are not visible."
        ),
        "solution_concept": solution,
        "solution_basis": solution_basis,
        "primary_responsibility": responsibility,
        "uncertainty": (
            "The internal severity and current workaround are unknown and must be "
            "confirmed before claiming this is a real company problem."
        ),
    }


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _bedrock_json_with_usage(
    prompt: str, model_id: str, region: str, max_tokens: int = 1800
) -> tuple[Record, Record]:
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1},
    )
    text = response["output"]["message"]["content"][0]["text"]
    usage = response.get("usage") or {}
    parsed = json.loads(_strip_fences(text))
    return parsed, {
        "input_tokens": int(usage.get("inputTokens", 0) or 0),
        "output_tokens": int(usage.get("outputTokens", 0) or 0),
        "total_tokens": int(usage.get("totalTokens", 0) or 0),
    }


def _bedrock_json(prompt: str, model_id: str, region: str) -> Record:
    parsed, _usage = _bedrock_json_with_usage(prompt, model_id, region)
    return parsed


def _add_site_evidence(record: Record) -> tuple[Record, str, list[str]]:
    """Attach evidence from the company's own site. Free, robots-respecting."""

    if os.getenv("ENABLE_COMPANY_SITE_RESEARCH", "true").casefold() not in {
        "1", "true", "yes",
    }:
        return record, "disabled", []
    evidence, emails, status = fetch_site_evidence(
        str(record.get("company_url") or "")
    )
    if not evidence:
        return record, status, emails
    copy = dict(record)
    existing = list(record.get("evidence") or [])
    seen = {
        canonical_url(item.get("url"))
        for item in existing
        if isinstance(item, dict)
    }
    copy["evidence"] = existing + [
        item for item in evidence if canonical_url(item["url"]) not in seen
    ]
    return copy, status, emails


def research_record(record: Record) -> Record:
    enriched, fetch_status = maybe_add_firecrawl_evidence(record)
    enriched, site_status, published_emails = _add_site_evidence(enriched)
    base = {
        **deterministic_research(enriched),
        "public_research_fetch_status": fetch_status,
        "site_evidence_status": site_status,
        "published_emails": published_emails,
    }
    if os.getenv("ENABLE_BEDROCK", "").casefold() not in {"1", "true", "yes"}:
        return base
    model_id = os.getenv("BEDROCK_RESEARCH_MODEL_ID", "")
    region = os.getenv("AWS_REGION", "")
    if not model_id or not region:
        return {**base, "llm_status": "skipped_missing_configuration"}
    prompt = json.dumps(
        {
                "instruction": (
                    "Use only the supplied evidence. Respond with ONLY a raw JSON "
                    "object with observed_problem_signal, inference, why_it_matters, "
                    "solution_concept, uncertainty. No markdown fences, no preamble, "
                    "no commentary outside the JSON. Never add facts, metrics, "
                    "people, URLs, or funding claims."
                ),
            "record": {
                "company": record.get("company"),
                "title": record.get("title"),
                "lane": record.get("lane"),
                "description": str(record.get("description", ""))[:12000],
                "evidence": base["evidence"],
            },
        },
        ensure_ascii=False,
    )
    try:
        generated, usage = _bedrock_json_with_usage(prompt, model_id, region)
    except Exception as exc:
        return {**base, "llm_status": "failed", "llm_error": str(exc)[:300]}
    allowed = {
        key: clean_text(generated.get(key))
        for key in (
            "observed_problem_signal",
            "inference",
            "why_it_matters",
            "solution_concept",
            "uncertainty",
        )
        if generated.get(key)
    }
    return {
        **base,
        **allowed,
        "llm_status": "ok",
        "model_id": model_id,
        "model_usage": usage,
    }


def research_funding_event(event: Record) -> Record:
    headline = clean_text(event.get("headline"))
    source_url = clean_text(event.get("source_url"))
    # Funding events arrive as a news headline, so they carry no company site of
    # their own. This runs anyway rather than guessing a domain: when a feed
    # starts supplying company_url the event gets the same evidence an
    # opportunity gets, and until then the status says plainly that it has none.
    event, site_status, published_emails = _add_site_evidence(event)
    base: Record = {
        "site_evidence_status": site_status,
        "published_emails": published_emails,
        "status": "provisional",
        "observed_signal": headline,
        "problem_hypothesis": "",
        "why_now": (
            "A newly reported funding event can create execution pressure, but the "
            "company's actual bottleneck is not public evidence."
        ),
        "solution_concept": "",
        "uncertainty": (
            "Validate the company's current priorities before treating any problem "
            "hypothesis as fact."
        ),
        "problem_status": "insufficient_evidence",
        "problem_evidence_urls": [source_url] if source_url else [],
    }
    if os.getenv("ENABLE_BEDROCK", "").casefold() not in {"1", "true", "yes"}:
        return base
    model_id = os.getenv("BEDROCK_RESEARCH_MODEL_ID", "")
    region = os.getenv("AWS_REGION", "")
    if not model_id or not region:
        return {**base, "llm_status": "skipped_missing_configuration"}
    prompt = json.dumps(
        {
            "instruction": (
                "Use only the supplied funding evidence. Return ONLY raw JSON with "
                "problem_hypothesis, why_now, solution_concept, uncertainty, and "
                "supported (boolean). A problem is an inference, never a known internal "
                "fact. Set supported=false when the evidence cannot ground a concrete "
                "hypothesis. Do not invent metrics, people, customers, products, URLs, "
                "locations, investors, or operational facts."
            ),
            "funding_event": {
                "company": event.get("company"),
                "headline": headline,
                "event_date": event.get("event_date"),
                "source_reported_detail": event.get("source_reported_detail"),
                "source_url": source_url,
                "source_confidence": event.get("source_confidence"),
            },
        },
        ensure_ascii=False,
    )
    try:
        generated, usage = _bedrock_json_with_usage(prompt, model_id, region)
    except Exception as exc:
        return {**base, "llm_status": "failed", "llm_error": str(exc)[:300]}
    supported = generated.get("supported") is True
    result = {
        **base,
        "llm_status": "ok",
        "model_id": model_id,
        "model_usage": usage,
        "problem_status": (
            "inference_needs_validation" if supported else "insufficient_evidence"
        ),
    }
    for key in ("problem_hypothesis", "why_now", "solution_concept", "uncertainty"):
        if generated.get(key):
            result[key] = clean_text(generated[key])
    if not supported:
        result["problem_hypothesis"] = ""
        result["solution_concept"] = ""
    return result

