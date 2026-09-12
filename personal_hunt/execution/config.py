from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


AUTOMATION_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = AUTOMATION_ROOT.parents[1]
CONFIG_ROOT = AUTOMATION_ROOT / "config"


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_ROOT / name
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_all() -> dict[str, dict[str, Any]]:
    return {
        "sources": load_yaml("sources.yml"),
        "scoring": load_yaml("scoring.yml"),
        "roles": load_yaml("roles.yml"),
        "models": load_yaml("models.yml"),
        "watchlist": load_yaml("watchlist.yml"),
    }


