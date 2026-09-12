from __future__ import annotations

import re
from pathlib import Path

from models import Record


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:60] or "company"


def _markdown(record: Record) -> str:
    research = record["research"]
    sources = "\n".join(
        f"- [{item['title']}]({item['url']}) - {item.get('observation') or 'Source record'} "
        f"(access/date: {item.get('date') or 'unavailable'})"
        for item in research.get("evidence", [])
    ) or "- No source-backed evidence beyond the opportunity record."
    return (
        f"# {record['company']} - evidence pack\n\n"
        f"Generated: {record['discovered_at']}\n\n"
        f"## Opportunity\n\n{record['title']} - score {record.get('score', 0)}/100\n\n"
        f"## Sources\n\n{sources}\n\n"
        f"## Observation\n\n{research['observed_problem_signal']}\n\n"
        f"## Inference - not a confirmed company fact\n\n{research['inference']}\n\n"
        f"## Why it may matter\n\n{research['why_it_matters']}\n\n"
        f"## Small solution concept\n\n{research['solution_concept']}\n\n"
        f"## Uncertainty to verify\n\n{research['uncertainty']}\n"
    )


def _prototype_markdown(record: Record) -> str:
    research = record["research"]
    return (
        f"# Micro-solution prototype: {record['company']}\n\n"
        f"Status: generated_unverified\n\n"
        f"## Evidence boundary\n\n{research['observed_problem_signal']}\n\n"
        f"## Hypothesis\n\n{research['inference']}\n\n"
        f"## Proposed artifact\n\n{research['solution_concept']}\n\n"
        "## Prototype acceptance check\n\n"
        "- Every input is linked to a public source.\n"
        "- Assumptions are visibly labeled.\n"
        "- The output can be reviewed in under five minutes.\n"
        "- No result metric is claimed before a real test.\n"
        "- Daksh manually approves the shareable version.\n\n"
        "## Next build step\n\n"
        "Verify the internal pain with the recipient or a second independent source, "
        "then turn this brief into the smallest useful spreadsheet, workflow, audit, "
        "dashboard, or runnable demo.\n"
    )


def create_artifacts(
    records: list[Record], output_root: Path, max_artifacts: int = 2
) -> list[Record]:
    evidence_root = output_root / "evidence"
    prototype_root = output_root / "prototypes"
    evidence_root.mkdir(parents=True, exist_ok=True)
    prototype_root.mkdir(parents=True, exist_ok=True)
    ranked = sorted(
        records,
        key=lambda item: (
            -len(item.get("research", {}).get("evidence", [])),
            -int(item.get("score", 0)),
            item["id"],
        ),
    )
    candidate_ids = {item["id"] for item in ranked[:max_artifacts]}
    for record in records:
        slug = f"{_slug(record['company'])}-{record['id'][-6:]}"
        evidence_path = evidence_root / f"{slug}.md"
        evidence_path.write_text(_markdown(record), encoding="utf-8")
        record["evidence_pack_path"] = str(evidence_path.resolve())
        record["artifact_status"] = "not_selected"
        if record["id"] in candidate_ids:
            prototype_path = prototype_root / f"{slug}.md"
            prototype_path.write_text(_prototype_markdown(record), encoding="utf-8")
            record["artifact_path"] = str(prototype_path.resolve())
            record["artifact_status"] = "generated_unverified"
    return records


