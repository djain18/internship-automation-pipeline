from __future__ import annotations

import sys
from pathlib import Path


EXECUTION = Path(__file__).resolve().parents[1] / "execution"
sys.path.insert(0, str(EXECUTION))


