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
            # Approved-outreach sender (2026-09-14). "shadow" mails Daksh the copies;
            # flip to "live" only after the shadow week, per the plan.
            "OUTREACH_SEND_MODE": "live",  # Daksh, 2026-09-14: live from 2026-09-15, no shadow week
            "OUTREACH_FROM": "dakshjainn02@gmail.com",
            "RESUME_DIR": "/data/resumes",
        }
    )
    .add_local_dir(PERSONAL_ROOT, remote_path="/root/personal-hunt")
    .add_local_dir(REPO_ROOT / "execution" / "hunt_core", remote_path="/root/execution/hunt_core")
)

api_image = (
    modal.Image.debian_slim(python_version="3.11")
    # 2026-09-14: the outreach review endpoints validate drafts with
    # check_draft -> outreach -> research, which pull these in.
    .pip_install(
        "fastapi[standard]>=0.115,<1",
        "firebase-admin>=6,<7",
        "beautifulsoup4>=4.12,<5",
        "boto3>=1.35,<2",
        "PyYAML>=6,<7",
        "requests>=2.32,<3",
    )
    .env(
        {
            "PIPELINE_OUTPUT_DIR": "/data/out",
            "PIPELINE_STATE_DIR": "/data/state",
            "PERSONAL_FRONTEND_ORIGINS": (
                "https://rise-web-kappa.vercel.app,http://localhost:5173"
            ),
        }
    )
    .add_local_dir(PERSONAL_ROOT / "execution", remote_path="/root/personal-hunt/execution")
    .add_local_dir(PERSONAL_ROOT / "templates", remote_path="/root/personal-hunt/templates")
    .add_local_dir(PERSONAL_ROOT / "config", remote_path="/root/personal-hunt/config")
    .add_local_dir(REPO_ROOT / "execution" / "hunt_core", remote_path="/root/execution/hunt_core")
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
    # 2026-09-13: switches on the already-credentialed firecrawl_research.py
    # (FIRECRAWL_API_KEY + ENABLE_FIRECRAWL_RESEARCH already live in
    # internship-hunt-secrets). A dedicated secret so this doesn't require
    # rewriting the bundle above, whose current contents can't be read back.
    modal.Secret.from_name("research-provider"),
    # 2026-09-13: internship-hunt-secrets' own FIRECRAWL_API_KEY started
    # returning 402 Payment Required on /v1/search (exhausted/dead, not a
    # tier restriction -- the free plan does include /search). Daksh
    # supplied a fresh free-tier key. Placed AFTER internship-hunt-secrets
    # in this list so its FIRECRAWL_API_KEY wins -- Modal secrets apply in
    # list order, later entries override earlier ones for the same env var.
    # Firecrawl is scoped to the funded-company resolution path only
    # (resolve_company_url_via_search); internship research stays free.
    modal.Secret.from_name("firecrawl-key"),
    # 2026-09-13: gmail.readonly token for the Sheet outcome sync
    # (gmail_outcomes.py). Created empty; the sync is a no-op until Daksh runs
    # `python personal_hunt/execution/mint_gmail_token.py --readonly` with the
    # account he sends outreach from and the token is pasted in.
    modal.Secret.from_name("internship-hunt-gmail-read"),
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
    volume.reload()  # drafts the routine submitted through personal_api
    arguments = ["--digest-latest", "--no-state"]
    if _self_digest_enabled():
        arguments.append("--send-digest")
    return _run(*arguments)


@app.function(
    image=pipeline_image,
    secrets=pipeline_secrets,
    volumes={"/data": volume},
    timeout=60 * 45,
    # The only cron this app may have (workspace limit: 5 scheduled functions,
    # 4 used elsewhere). Must match schedule_slots.CRON; job_for picks the job.
    schedule=modal.Cron("0,30 10,18,21 * * *", timezone="Asia/Kolkata"),
)
def scheduled_pipeline() -> dict[str, object]:
    sys.path.insert(0, "/root/personal-hunt/execution")
    from schedule_slots import job_for

    job = job_for(datetime.now(ZoneInfo("Asia/Kolkata")))
    if job == "collect":
        return collect.local()
    if job == "deliver":
        return deliver.local()
    if job == "send":
        return send_approved_emails.local()
    return {"status": "no_job_at_this_time"}


@app.function(
    image=pipeline_image,
    secrets=pipeline_secrets,
    volumes={"/data": volume},
    timeout=60 * 30,
)
def send_approved_emails() -> dict[str, object]:
    # Run at 10:00 IST Mon-Fri by scheduled_pipeline. Belkins 2026 (7.5M cold
    # emails): 8 AM-noon has the highest reply rate; approvals lock at 09:00.
    sys.path.insert(0, "/root/personal-hunt/execution")
    sys.path.insert(0, "/root")
    volume.reload()  # pick up approvals committed by personal_api
    import send_approved

    return send_approved.run_slot(commit=volume.commit)


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
    # outreach-routine-token: RISE_OUTREACH_TOKEN, the drafting routine's bearer
    # secret for /api/outreach/queue and /api/outreach/drafts (2026-09-14).
    secrets=[modal.Secret.from_name("firebase-admin-key"), modal.Secret.from_name("outreach-routine-token")],
    volumes={"/data": volume},
    timeout=60,
)
@modal.asgi_app()
def personal_api():
    sys.path.insert(0, "/root/personal-hunt/execution")
    import private_api

    # Draft edits and approvals must reach the sender's container.
    private_api.COMMIT = volume.commit
    return private_api.app


@app.local_entrypoint()
def smoke(fixtures: bool = True) -> None:
    result = fixture_pipeline.remote() if fixtures else live_render_pipeline.remote()
    print(json.dumps(result, indent=2))
