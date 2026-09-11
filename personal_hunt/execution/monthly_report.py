from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from models import Record


DIMENSIONS = ("source", "role_family", "contact_type", "strategy_id")


def build_monthly_report(rows: Iterable[Record], minimum_sends: int = 10) -> Record:
    """Aggregate observed outcomes only; this report never mutates scoring weights."""
    groups: dict[str, dict[str, Record]] = {dimension: defaultdict(dict) for dimension in DIMENSIONS}
    for row in rows:
        for dimension in DIMENSIONS:
            value = str(row.get(dimension) or "unknown")
            bucket = groups[dimension].setdefault(
                value, {"records": 0, "sends": 0, "replies": 0, "interviews": 0}
            )
            bucket["records"] += 1
            if row.get("sent_at"):
                bucket["sends"] += 1
            if row.get("reply_outcome") not in (None, "", "no_reply"):
                bucket["replies"] += 1
            if row.get("interview_outcome") not in (None, "", "none", "no_interview"):
                bucket["interviews"] += 1
    result: Record = {"minimum_sends": minimum_sends, "scoring_weights_changed": False, "groups": {}}
    for dimension, values in groups.items():
        result["groups"][dimension] = {
            key: {**counts, "sample_status": "sufficient" if counts["sends"] >= minimum_sends else "insufficient_sample"}
            for key, counts in sorted(values.items())
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the offline personal-hunt outcome report")
    parser.add_argument("input", type=Path, help="JSON array of exported tracking rows")
    parser.add_argument("--output", type=Path, help="Optional JSON report destination")
    parser.add_argument("--minimum-sends", type=int, default=10)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Input must be a JSON array")
    rendered = json.dumps(
        build_monthly_report(rows, minimum_sends=args.minimum_sends),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
