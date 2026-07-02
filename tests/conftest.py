"""Shared pytest setup: make the repo's modules importable from tests."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for path in (ROOT, os.path.join(ROOT, "execution"), os.path.join(ROOT, "api")):
    if path not in sys.path:
        sys.path.insert(0, path)
