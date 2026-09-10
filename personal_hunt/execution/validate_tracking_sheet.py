from __future__ import annotations

import argparse
from collections import Counter
import json
import os

from sheets import TAB_SCHEMAS, _service


def validate_headers(expected: list[str], actual: list[str]) -> dict[str, object]:
    counts = Counter(actual)
    missing = [header for header in expected if header not in counts]
    duplicates = [header for header, count in counts.items() if header and count > 1]
    return {
        "valid": not missing and not duplicates,
        "missing_headers": missing,
        "duplicate_headers": sorted(duplicates),
        "extra_headers": [header for header in actual if header not in expected],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate tracking Sheet tabs and rows")
    parser.add_argument("--spreadsheet-id", default=os.getenv("INTERNSHIP_SHEET_ID", ""))
    args = parser.parse_args()
    if not args.spreadsheet_id:
        raise RuntimeError("INTERNSHIP_SHEET_ID or --spreadsheet-id is required")
    service = _service()
    report = {}
    valid = True
    for tab, expected_headers in TAB_SCHEMAS.items():
        values = service.spreadsheets().values().get(
            spreadsheetId=args.spreadsheet_id,
            range=f"'{tab}'!A:ZZ",
        ).execute().get("values", [])
        headers = values[0] if values else []
        header_result = validate_headers(expected_headers, headers)
        matches = bool(header_result["valid"])
        valid = valid and matches
        report[tab] = {
            "data_rows": max(len(values) - 1, 0),
            "headers_match": matches,
            **{key: value for key, value in header_result.items() if key != "valid"},
        }
    print(json.dumps({"valid": valid, "tabs": report}, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

