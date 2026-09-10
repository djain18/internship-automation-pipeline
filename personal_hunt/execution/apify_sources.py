from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from models import Record, clean_text, utc_timestamp
from state import LocalState


APIFY_API = "https://api.apify.com/v2"


def account_monthly_usage(token: str, timeout: int = 20) -> tuple[float, float]:
    """Return current account usage and provider cap; paid work fails closed."""

    response = requests.get(
        f"{APIFY_API}/users/me/limits",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json().get("data") or {}
    used = float((data.get("current") or {}).get("monthlyUsageUsd") or 0)
    provider_cap = float((data.get("limits") or {}).get("maxMonthlyUsageUsd") or 0)
    return used, provider_cap


def actor_health_status(actor_status: str, record_count: int) -> str:
    """Translate Apify's run status into the pipeline health vocabulary."""
    normalized = clean_text(actor_status).upper()
    if normalized == "SUCCEEDED":
        return "ok" if record_count else "zero_results"
    return "failed"


def _state() -> LocalState:
    state_dir = Path(os.getenv("PIPELINE_STATE_DIR", str(Path(__file__).parents[1] / "state")))
    return LocalState(state_dir / "state.json")


def _actor_key(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def _map_linkedin(items: list[Record], source: dict[str, Any]) -> list[Record]:
    output: list[Record] = []
    for item in items:
        text = clean_text(item.get("text") or item.get("content") or item.get("postText"))
        url = item.get("linkedinUrl") or item.get("postUrl") or item.get("url")
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        posted_at = item.get("postedAt")
        if isinstance(posted_at, dict):
            posted_at = posted_at.get("date") or posted_at.get("timestamp")
        output.append(
            {
                "source": source["id"],
                "id": item.get("id") or item.get("urn") or url,
                "company": clean_text(
                    item.get("companyName") or author.get("name") or item.get("authorName")
                ),
                "title": clean_text(item.get("title") or text[:160]),
                "description": text,
                "location": clean_text(item.get("location")),
                "source_url": url,
                "apply_url": item.get("applyUrl") or url,
                "posted_at": posted_at or item.get("publishedAt"),
                "source_confidence": "low",
                "verification_status": "machine_collected_unverified",
                "source_priority": source.get("source_priority", 99),
            }
        )
    return output


def _map_x(items: list[Record], source: dict[str, Any]) -> list[Record]:
    output: list[Record] = []
    for item in items:
        text = clean_text(item.get("text") or item.get("fullText") or item.get("rawContent"))
        author_value = item.get("author") or item.get("user")
        author = author_value if isinstance(author_value, dict) else {}
        url = item.get("url") or item.get("tweetUrl")
        output.append(
            {
                "source": source["id"],
                "id": item.get("id_str") or item.get("id") or item.get("tweetId") or url,
                "company": clean_text(
                    author.get("displayname") or author.get("name") or item.get("authorName")
                ),
                "title": clean_text(item.get("title") or text[:160]),
                "description": text,
                "location": clean_text(item.get("location")),
                "source_url": url,
                "apply_url": item.get("applyUrl") or url,
                "posted_at": item.get("date") or item.get("createdAt"),
                "source_confidence": "low",
                "verification_status": "machine_collected_unverified",
                "source_priority": source.get("source_priority", 99),
            }
        )
    return output


def _map_careers(items: list[Record], source: dict[str, Any]) -> list[Record]:
    output: list[Record] = []
    for item in items:
        url = item.get("sourceUrl") or item.get("jobUrl") or item.get("url")
        output.append(
            {
                "source": source["id"],
                "id": item.get("id") or item.get("jobId") or url,
                "company": clean_text(item.get("company") or item.get("companyName")),
                "title": clean_text(item.get("title") or item.get("jobTitle")),
                "description": clean_text(item.get("description") or item.get("descriptionText")),
                "location": clean_text(item.get("location") or item.get("locations")),
                "source_url": url,
                "apply_url": item.get("applyUrl") or url,
                "posted_at": item.get("publishedAt"),
                "employment_type": item.get("employmentType"),
                "source_confidence": "medium",
                "verification_status": "machine_collected",
                "source_priority": source.get("source_priority", 99),
            }
        )
    return output


def map_actor_items(items: list[Record], source: dict[str, Any]) -> list[Record]:
    adapter = source.get("adapter")
    if adapter == "apify_linkedin_posts":
        return _map_linkedin(items, source)
    if adapter == "apify_x_posts":
        return _map_x(items, source)
    if adapter == "apify_career_pages":
        return _map_careers(items, source)
    raise ValueError(f"unknown Apify adapter: {adapter}")


def fetch_apify_actor(
    source: dict[str, Any], apify_config: dict[str, Any], timeout: int
) -> tuple[list[Record], Record]:
    token = os.getenv("APIFY_TOKEN", "") or os.getenv("APIFY_API_TOKEN", "")
    if not token:
        raise RuntimeError("APIFY_TOKEN is required for an enabled Apify source")
    actor_input = source.get("input")
    if not isinstance(actor_input, dict) or not actor_input:
        raise RuntimeError("Apify actor input is empty; capped contract is not configured")
    state = _state()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    budget = float(apify_config.get("monthly_budget_usd", 5.0))
    warn_at = float(apify_config.get("warn_at_usd", budget))
    run_charge_cap = float(apify_config.get("max_run_charge_usd", 0.25))
    if run_charge_cap <= 0:
        raise ValueError("Apify max_run_charge_usd must be positive")
    used, provider_cap = account_monthly_usage(token, timeout=min(timeout, 20))
    effective_cap = min(budget, provider_cap) if provider_cap > 0 else budget
    if used + run_charge_cap > effective_cap:
        raise RuntimeError(
            f"Apify monthly hard stop: ${used:.2f} used; "
            f"a ${run_charge_cap:.2f} capped run exceeds ${effective_cap:.2f}"
        )
    response = requests.post(
        f"{APIFY_API}/acts/{_actor_key(source['actor_id'])}/runs",
        params={
            "token": token,
            "waitForFinish": min(int(source.get("wait_seconds", 120)), 300),
            "maxTotalChargeUsd": round(run_charge_cap, 2),
        },
        json=actor_input,
        timeout=max(timeout, int(source.get("wait_seconds", 120)) + 30),
    )
    response.raise_for_status()
    run = response.json().get("data") or {}
    run_id = clean_text(run.get("id"))
    status = clean_text(run.get("status"))
    if status not in {"SUCCEEDED", "TIMED-OUT", "FAILED", "ABORTED"}:
        status_response = requests.get(
            f"{APIFY_API}/actor-runs/{run_id}",
            params={"token": token, "waitForFinish": 60},
            timeout=90,
        )
        status_response.raise_for_status()
        run = status_response.json().get("data") or run
        status = clean_text(run.get("status"))
    dataset_id = clean_text(run.get("defaultDatasetId"))
    items: list[Record] = []
    if dataset_id:
        item_response = requests.get(
            f"{APIFY_API}/datasets/{dataset_id}/items",
            params={
                "token": token,
                "clean": "true",
                "limit": int(source.get("max_items", 50)),
            },
            timeout=timeout,
        )
        item_response.raise_for_status()
        payload = item_response.json()
        if isinstance(payload, list):
            items = [item for item in payload if isinstance(item, dict)]
    usage = float(run.get("usageTotalUsd", 0) or 0)
    checked_at = utc_timestamp()
    state.record_apify_run(
        month, source["actor_id"], run_id, usage, len(items), status, checked_at
    )
    mapped = map_actor_items(items, source)
    return mapped, {
        "health_status": actor_health_status(status, len(mapped)),
        "actor_status": status.casefold(),
        "actor_id": source["actor_id"],
        "actor_run_id": run_id,
        "usage_total_usd": usage,
        "month_spend_usd": state.apify_month_spend(month),
        "account_month_spend_usd": used + usage,
        "monthly_hard_stop_usd": effective_cap,
        "budget_warning": state.apify_month_spend(month) >= warn_at,
    }
