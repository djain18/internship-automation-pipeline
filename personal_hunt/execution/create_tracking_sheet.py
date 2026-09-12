from __future__ import annotations

import argparse
import json

from sheets import create_tracking_sheet


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the internship hunt Google Sheet")
    parser.add_argument("--title", default="Daksh Internship Hunt 2026-27")
    args = parser.parse_args()
    print(json.dumps(create_tracking_sheet(args.title), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


