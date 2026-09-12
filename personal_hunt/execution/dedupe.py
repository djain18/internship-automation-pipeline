from __future__ import annotations

from models import Record, canonical_url, clean_text


def _key(record: Record) -> tuple[str, ...]:
    apply_url = canonical_url(record.get("apply_url"))
    source_url = canonical_url(record.get("source_url"))
    if apply_url:
        return ("apply", apply_url)
    if source_url:
        return ("source", source_url)
    return (
        "identity",
        clean_text(record.get("company")).casefold(),
        clean_text(record.get("title")).casefold(),
        clean_text(record.get("location_class")).casefold(),
    )


def _quality(record: Record) -> tuple[int, int, int]:
    evidence_count = len(record.get("evidence") or [])
    field_count = sum(bool(value) for value in record.values())
    confidence = {"official": 4, "high": 3, "medium": 2, "low": 1}.get(
        str(record.get("source_confidence", "")).casefold(), 0
    )
    return confidence, evidence_count, field_count


def deduplicate(records: list[Record]) -> tuple[list[Record], list[Record]]:
    kept: dict[tuple[str, ...], Record] = {}
    dropped: list[Record] = []
    for record in records:
        key = _key(record)
        current = kept.get(key)
        if current is None:
            kept[key] = record
            continue
        if _quality(record) > _quality(current):
            current["duplicate_of"] = record["id"]
            dropped.append(current)
            kept[key] = record
        else:
            record["duplicate_of"] = current["id"]
            dropped.append(record)
    return list(kept.values()), dropped


