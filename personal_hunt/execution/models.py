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


