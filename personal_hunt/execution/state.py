from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LocalState:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "runs": {},
                "seen_opportunities": {},
                "digest_deliveries": {},
                "sent_opportunity_ids": [],
                "apify_spend": {},
                "role_judgements": {},
            }
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("state file must contain a JSON object")
        payload.setdefault("runs", {})
        payload.setdefault("seen_opportunities", {})
        payload.setdefault("digest_deliveries", {})
        payload.setdefault("sent_opportunity_ids", [])
        payload.setdefault("apify_spend", {})
        payload.setdefault("role_judgements", {})
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def record_run(self, run: dict[str, Any]) -> None:
        state = self.load()
        run_id = str(run["run_id"])
        state["runs"][run_id] = {
            "status": run.get("status"),
            "run_date": run.get("run_date"),
            "completed_at": run.get("completed_at"),
            "primary_count": len(run.get("primary", [])),
            "remote_count": len(run.get("remote_fallback", [])),
        }
        for record in run.get("all_scored", []):
            previous = state["seen_opportunities"].get(record["id"], {})
            state["seen_opportunities"][record["id"]] = {
                "first_seen": previous.get("first_seen")
                or previous.get("last_seen")
                or record.get("first_discovered_at")
                or run.get("run_date"),
                "last_seen": run.get("run_date"),
                "company": record.get("company"),
                "title": record.get("title"),
            }
        judgements = run.get("role_judgement_cache")
        if isinstance(judgements, dict):
            state.setdefault("role_judgements", {}).update(judgements)
        self.save(state)

    def first_seen_dates(self) -> dict[str, str]:
        state = self.load()
        return {
            str(identifier): str(item.get("first_seen") or item.get("last_seen"))
            for identifier, item in state.get("seen_opportunities", {}).items()
            if isinstance(item, dict) and (item.get("first_seen") or item.get("last_seen"))
        }

    def role_judgements(self) -> dict[str, Any]:
        state = self.load()
        value = state.get("role_judgements", {})
        return dict(value) if isinstance(value, dict) else {}

    def digest_delivery(self, run_id: str) -> dict[str, Any]:
        state = self.load()
        value = state.get("digest_deliveries", {}).get(run_id, {})
        return dict(value) if isinstance(value, dict) else {}

    def sent_opportunity_ids(self) -> set[str]:
        state = self.load()
        return {str(value) for value in state.get("sent_opportunity_ids", [])}

    def record_digest_delivery(
        self,
        run_id: str,
        recipient: str,
        message_id: str,
        sent_at: str,
        opportunity_ids: list[str] | None = None,
    ) -> None:
        state = self.load()
        deliveries = state.setdefault("digest_deliveries", {})
        deliveries[run_id] = {
            "recipient": recipient,
            "message_id": message_id,
            "sent_at": sent_at,
            "opportunity_ids": list(opportunity_ids or []),
        }
        existing_ids = {str(value) for value in state.get("sent_opportunity_ids", [])}
        existing_ids.update(str(value) for value in (opportunity_ids or []))
        state["sent_opportunity_ids"] = sorted(existing_ids)
        self.save(state)

    def apify_month_spend(self, month: str) -> float:
        state = self.load()
        bucket = state.get("apify_spend", {}).get(month, {})
        runs = bucket.get("runs", {}) if isinstance(bucket, dict) else {}
        return round(
            sum(float(item.get("usage_total_usd", 0) or 0) for item in runs.values()),
            6,
        )

    def record_apify_run(
        self,
        month: str,
        actor_id: str,
        run_id: str,
        usage_total_usd: float,
        item_count: int,
        status: str,
        checked_at: str,
    ) -> None:
        state = self.load()
        bucket = state.setdefault("apify_spend", {}).setdefault(month, {"runs": {}})
        bucket.setdefault("runs", {})[run_id] = {
            "actor_id": actor_id,
            "usage_total_usd": round(float(usage_total_usd), 6),
            "item_count": int(item_count),
            "status": status,
            "checked_at": checked_at,
        }
        self.save(state)
