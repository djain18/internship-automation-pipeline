from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from models import utc_timestamp


@dataclass
class SourceHealth:
    source_id: str
    status: str
    record_count: int = 0
    latency_ms: int = 0
    error_type: str = ""
    error_message: str = ""
    checked_at: str = ""
    human_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        if not self.checked_at:
            self.checked_at = utc_timestamp()
        return asdict(self)


def classify_http_failure(status_code: int) -> tuple[str, str]:
    if status_code in {401, 403}:
        return "access_control", "Disable the adapter and verify an authorized public route."
    if status_code == 429:
        return "rate_limited", "Retry later with lower frequency; do not evade the limit."
    if status_code >= 500:
        return "temporary_upstream", "Retry with bounded exponential backoff."
    return "http_error", "Inspect the documented public endpoint and source contract."


