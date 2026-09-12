from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


Record = dict[str, Any]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def iso_date(value: date | None = None) -> str:
    return (value or datetime.now(timezone.utc).date()).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", text).strip()


def repair_mojibake(text: str) -> str:
    """Undo UTF-8 bytes that were decoded as cp1252 upstream (e.g. an
    apostrophe arriving as "Founderâ€™s Office", or a rupee sign arriving
    as "â‚¹532 Cr"). Downstream exact-quote validators (llm_rank.py's
    LinkedIn extraction, this module's own consumers) need a literal
    substring match against the original text, so mangled punctuation
    silently loses otherwise-good records. Only applied when the round
    trip succeeds cleanly; genuinely correct text that happens to contain
    cp1252-range characters almost never round-trips through cp1252 into
    valid UTF-8 by coincidence, so the safety is in the round trip itself,
    not this pre-check -- the pre-check only exists to skip the encode/
    decode attempt on plain-ASCII text.

    Bug fixed 2026-09-13: an earlier version of this check required the
    literal two-character sequence "â€" (U+00E2 U+20AC), which covers
    apostrophes, dashes and ellipses but not other mojibaked punctuation
    such as the rupee sign (U+00E2 U+201A U+00B9). Any occurrence of
    U+00E2 or U+00C2 is a 3-byte or 2-byte UTF-8 lead byte misread as
    cp1252, so either alone is enough to attempt the repair."""
    if not text or ("Â" not in text and "â" not in text):
        return text
    try:
        repaired = text.encode("cp1252").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text
    return repaired


def canonical_url(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"ref", "source", "trk", "tracking"}
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def stable_id(*parts: Any, prefix: str = "opp") -> str:
    normalized = "|".join(clean_text(part).casefold() for part in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def normalized_content_hash(value: Any) -> str:
    """Hash semantic JSON content with stable key ordering and whitespace."""
    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(key): normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if isinstance(item, str):
            return clean_text(item)
        return item

    normalized = json_dumps(normalize(value))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def llm_cache_key(
    purpose: str, model_id: str, prompt_version: str, content: Any
) -> tuple[str, str]:
    """Return a policy-aware cache key and the underlying content hash."""
    content_hash = normalized_content_hash(content)
    key_material = {
        "purpose": clean_text(purpose),
        "model_id": clean_text(model_id),
        "prompt_version": clean_text(prompt_version),
        "content_hash": content_hash,
    }
    return f"llm_{normalized_content_hash(key_material)}", content_hash


def usage_summary(items: list[Record]) -> Record:
    """Aggregate provider usage and cache activity for one run."""
    return {
        "calls": sum(int(item.get("calls", 0) or 0) for item in items),
        "cache_hits": sum(int(item.get("cache_hits", 0) or 0) for item in items),
        "input_tokens": sum(int(item.get("input_tokens", 0) or 0) for item in items),
        "output_tokens": sum(int(item.get("output_tokens", 0) or 0) for item in items),
        "total_tokens": sum(int(item.get("total_tokens", 0) or 0) for item in items),
        "elapsed_ms": sum(int(item.get("elapsed_ms", 0) or 0) for item in items),
        "cost_usd": round(
            sum(float(item.get("cost_usd", 0) or 0) for item in items), 8
        ),
    }
