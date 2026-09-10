"""Low-volume application-link validation without access-control bypasses."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests


def validate_application_link(url: str, timeout: int = 8) -> dict[str, Any]:
    value = str(url or "").strip()
    if not value:
        return {"status": "missing", "definitively_dead": False}
    if value.startswith("mailto:"):
        return {"status": "mailto", "definitively_dead": False}
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"status": "invalid", "definitively_dead": True}

    headers = {"User-Agent": "RiseInternshipResearch/1.0 (+manual review; low-volume)"}
    try:
        response = requests.head(
            value, timeout=timeout, allow_redirects=True, headers=headers
        )
        if response.status_code == 405:
            response = requests.get(
                value,
                timeout=timeout,
                allow_redirects=True,
                headers={**headers, "Range": "bytes=0-1024"},
                stream=True,
            )
        status_code = int(response.status_code)
        if status_code in {404, 410}:
            return {
                "status": "dead",
                "status_code": status_code,
                "definitively_dead": True,
            }
        if 200 <= status_code < 400:
            return {
                "status": "active",
                "status_code": status_code,
                "definitively_dead": False,
                "resolved_url": response.url,
            }
        return {
            "status": "verification_required",
            "status_code": status_code,
            "definitively_dead": False,
        }
    except requests.RequestException as exc:
        return {
            "status": "verification_required",
            "definitively_dead": False,
            "warning": f"{type(exc).__name__}: {str(exc)[:180]}",
        }

