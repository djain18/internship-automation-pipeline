"""Run the Modal CLI with the Windows system CA store enabled.

Usage: python scripts/modal_system_ca.py app list
       python scripts/modal_system_ca.py deploy personal_hunt/deploy/modal_app.py
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from execution.hunt_core.network import enable_system_ca


def main() -> None:
    enable_system_ca()
    sys.argv = ["modal", *sys.argv[1:]]
    runpy.run_module("modal", run_name="__main__")


if __name__ == "__main__":
    main()

