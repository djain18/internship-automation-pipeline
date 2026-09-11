from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import modal


APP_NAME = "daksh-internship-hunt"
_FILE_PARENTS = Path(__file__).resolve().parents
# ponytail: only used for local image-build declarations below; remote
# containers re-import this module flat at /root/modal_app.py (no deploy/
# personal_hunt ancestry), so fall back to the shallowest parent available
# instead of indexing past the end.
REPO_ROOT = _FILE_PARENTS[2] if len(_FILE_PARENTS) > 2 else _FILE_PARENTS[-1]
PERSONAL_ROOT = _FILE_PARENTS[1] if len(_FILE_PARENTS) > 1 else _FILE_PARENTS[-1]

volume = modal.Volume.from_name("internship-hunt-data", create_if_missing=True)

pipeline_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "beautifulsoup4>=4.12,<5",
        "boto3>=1.35,<2",
        "feedparser>=6,<7",
        "google-api-python-client>=2.140,<3",
        "google-auth>=2.34,<3",
        "PyYAML>=6,<7",
        "requests>=2.32,<3",
    )
    .env(
        {
            "PIPELINE_OUTPUT_DIR": "/data/out",
            "PIPELINE_STATE_DIR": "/data/state",
            "PERSONAL_HUNT_URL": "https://rise-web-kappa.vercel.app/my-hunt",
        }
    )
    .add_local_dir(PERSONAL_ROOT, remote_path="/root/personal-hunt")
    .add_local_dir(REPO_ROOT / "execution" / "hunt_core", remote_path="/root/execution/hunt_core")
)

api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]>=0.115,<1", "firebase-admin>=6,<7")
    .env(
        {
            "PIPELINE_OUTPUT_DIR": "/data/out",
            "PIPELINE_STATE_DIR": "/data/state",
            "PERSONAL_FRONTEND_ORIGINS": (
                "https://rise-web-kappa.vercel.app,http://localhost:5173"
            ),
        }
    )
    .add_local_file(
        PERSONAL_ROOT / "execution" / "private_api.py",
        remote_path="/root/private_api.py",
    )
)

app = modal.App(APP_NAME)
pipeline_secrets = [
    modal.Secret.from_name("internship-hunt-secrets"),
    modal.Secret.from_name("internship-hunt-gmail"),
    modal.Secret.from_name("internship-hunt-self-digest"),
    # The public-post actor runs every scheduled run (linkedin_every_run),
    # stays low-confidence, and is bounded by per-slot usage checks plus
    # maxTotalChargeUsd. Keys come from APIFY_TOKEN_1..7 in this secret.
    modal.Secret.from_name("apify-token"),
    # Rise's GOOGLE_SHEET_ID only, for the rise_public_sheet ingestion source
    # (spec: fetch the Rise live Sheet as upstream source 1). Deliberately
    # scoped to this one value, not the full internship-secrets bundle.
    modal.Secret.from_name("rise-sheet-id"),
]


def _run(*arguments: str) -> dict[str, object]:
    command = [
        sys.executable,
        "/root/personal-hunt/execution/pipeline.py",
        *arguments,
    ]
    environment = dict(os.environ)
    environment["AWS_REGION"] = "ap-south-1"
    environment["BEDROCK_RESEARCH_MODEL_ID"] = "moonshotai.kimi-k2.5"
    result = subprocess.run(
        command, capture_output=True, text=True, env=environment
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-1500:]
        raise RuntimeError(f"pipeline {' '.join(arguments)} failed: {tail}")
    return json.loads(result.stdout)


def _self_digest_enabled() -> bool:
    return os.getenv("ENABLE_SELF_DIGEST", "false").casefold() in {"1", "true", "yes"}


@app.function(
    image=pipeline_image,
    secrets=pipeline_secrets,
    volumes={"/data": volume},
    timeout=60 * 45,
)
def collect() -> dict[str, object]:
    arguments = ["--live"]
    if os.getenv("ENABLE_PERSONAL_APIFY_TOPUP", "false").casefold() in {
        "1", "true", "yes"
    }:
        arguments.append("--allow-paid-sources")
    if os.getenv("INTERNSHIP_SHEET_ID"):
        arguments.append("--publish-sheets")
    return _run(*arguments)


@app.function(
    image=pipeline_image,
    secrets=pipeline_secrets,
    volumes={"/data": volume},
    timeout=60 * 10,
)
def deliver() -> dict[str, object]:
    arguments = ["--digest-latest", "--no-state"]
    if _self_digest_enabled():
        arguments.append("--send-digest")
    return _run(*arguments)


@app.function(
    image=pipeline_image,
    secrets=pipeline_secrets,
    volumes={"/data": volume},
    timeout=60 * 45,
    schedule=modal.Cron("30 0,8 * * *", timezone="Asia/Kolkata"),
)
def scheduled_pipeline() -> dict[str, object]:
    hour = datetime.now(ZoneInfo("Asia/Kolkata")).hour
    return deliver.local() if 7 <= hour < 12 else collect.local()


@app.function(
    image=pipeline_image,
    secrets=pipeline_secrets,
    volumes={"/data": volume},
    timeout=60 * 10,
)
def fixture_pipeline() -> dict[str, object]:
    return _run("--fixtures", "--no-state")


@app.function(
    image=pipeline_image,
    secrets=pipeline_secrets,
    volumes={"/data": volume},
    timeout=60 * 45,
)
def live_render_pipeline() -> dict[str, object]:
    return _run("--live", "--dry-run")


@app.function(
    image=api_image,
    secrets=[modal.Secret.from_name("firebase-admin-key")],
    volumes={"/data": volume},
    timeout=60,
)
@modal.asgi_app()
def personal_api():
    sys.path.insert(0, "/root")
    from private_api import app as fastapi_app

    return fastapi_app


@app.local_entrypoint()
def smoke(fixtures: bool = True) -> None:
    result = fixture_pipeline.remote() if fixtures else live_render_pipeline.remote()
    print(json.dumps(result, indent=2))
