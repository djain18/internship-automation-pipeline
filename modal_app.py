"""
modal_app.py
-------------
Modal serverless deployment for the Internship Pipeline.

Features:
- Scheduled cron job (daily 11PM IST = 5:30PM UTC)
- Webhook trigger for manual runs
- Secrets management via Modal
- Pay-per-second billing

Usage:
    modal deploy modal_app.py
    curl https://dakshinjain187--internship-pipeline-run-now.modal.run
"""

import modal
import json
import os
import subprocess
import sys

# Create Modal app
app = modal.App("internship-pipeline")

# Define the image with dependencies and local files
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "apify-client",
        "python-dotenv",
        "google-auth",
        "google-auth-oauthlib",
        "google-api-python-client",
        "requests",
        "fastapi[standard]",
        "google-genai",          # Replaces deprecated google-generativeai
        "groq",
        "openai",
        "boto3",                 # AWS Bedrock (GLM 5) — primary LLM provider
        "python-dateutil",
        "firebase-admin",
    )
    .add_local_dir("execution", remote_path="/app/execution")
    .add_local_file("run_pipeline.py", remote_path="/app/run_pipeline.py")
    .add_local_file("extraction_prompt.txt", remote_path="/app/extraction_prompt.txt")
    .add_local_file("token.json", remote_path="/app/token.json")
)

# ── Lightweight image for the website API — deliberately NOT the pipeline's
# heavy image (apify-client, google-genai, groq, openai etc. are not needed
# here and would add cold-start weight to a public-facing endpoint). ──
api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]==0.115.5",
        "uvicorn[standard]==0.32.1",
        "httpx==0.27.2",
        "pydantic[email]==2.10.3",
        "python-dotenv==1.0.1",
    )
    .add_local_dir("api", remote_path="/app/api")
    # api/sheets.py imports role_taxonomy for its cluster labels. This image
    # deliberately does NOT mount execution/ (it would drag the pipeline's
    # weight onto a public endpoint), so the one dependency-free module it
    # needs is mounted flat beside it — api/sheets.py falls back to that import
    # path. Without this line api_web fails to import in production.
    .add_local_file("execution/role_taxonomy.py",
                    remote_path="/app/api/role_taxonomy.py")
)


def _setup_env():
    """Common setup: create credential files from Modal secrets."""
    os.chdir("/app")
    os.makedirs(".tmp", exist_ok=True)

    # 2026-08-22: nightly's default 24h scrape window was chronically
    # under-supplying genuine posts (7 published vs a soft target of 35).
    # A live A/B on the same night showed a widened window nearly quadrupling
    # raw supply (48 -> ~437 raw posts) and tripling genuine publishes (7 ->
    # 30), with no change to the quality gate — _pre_filter_posts still hard-
    # rejects anything older than ~4 days regardless of this setting, so this
    # doesn't relax anti-spam filtering, only gives it more raw material.
    # setdefault so an explicit Modal secret value (or a local override for a
    # manual catch-up run) still wins.
    os.environ.setdefault("SCRAPE_POSTED_LIMIT", "week")

    if os.getenv("GOOGLE_CREDENTIALS_JSON"):
        with open("credentials.json", "w") as f:
            f.write(os.getenv("GOOGLE_CREDENTIALS_JSON"))
    
    if os.getenv("GOOGLE_TOKEN_JSON") and not os.path.exists("token.json"):
        with open("token.json", "w") as f:
            f.write(os.getenv("GOOGLE_TOKEN_JSON"))
            
    # DIAGNOSTIC: Confirm Apify token is present and match user's expectation
    apify_token = os.getenv("APIFY_API_TOKEN")
    if apify_token:
        print(f"✅ APIFY_API_TOKEN detected: {apify_token[:8]}...{apify_token[-4:]}")
    else:
        print("❌ APIFY_API_TOKEN NOT DETECTED")


def _run_script(script_path, timeout=600):
    """Helper to run a script and stream output/errors in real-time."""
    print(f"\n>> Step: {script_path}...")
    try:
        # Simplest way: let subprocess write directly to our stdout/stderr
        result = subprocess.run(
            [sys.executable, script_path],
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        
        if result.returncode == 0:
            print(f"   [OK] {script_path}")
            return "success"
        else:
            print(f"   [FAIL] {script_path} (Exit {result.returncode})")
            return "failed"
            
    except subprocess.TimeoutExpired:
        print(f"   [TIMEOUT] {script_path} exceeded {timeout}s")
        return "timeout"
    except Exception as e:
        print(f"   [ERROR] {script_path}: {e}")
        return f"error: {e}"


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
    ],
    timeout=3600,  # 60 minutes
    memory=2048,   # 2GB RAM to prevent OOM during multi-threading
)
def run_pipeline():
    """
    Run the full internship pipeline using the master orchestrator script.
    """
    _setup_env()
    
    print("=" * 60)
    print("INTERNSHIP PIPELINE - MODAL CLOUD TRIGGER")
    print("=" * 60)
    
    # Aligning the internal Modal timeout safely up against the 3600s hard ceiling.
    run_status = _run_script("run_pipeline.py", timeout=3500)
    
    # Final count reporting
    final_count = 0
    if os.path.exists(".tmp/final_ranked_internships.json"):
        try:
            with open(".tmp/final_ranked_internships.json") as f:
                final_count = len(json.load(f))
        except Exception:
            pass
    
    print(f"\n{'=' * 60}")
    print(f"MODAL COMPLETE — {final_count} internships extracted via Unified Script")
    print(f"Orchestrator Result: {run_status}")
    print('=' * 60)
    
    return {
        "status": "completed" if run_status == "success" else run_status,
        "internships_count": final_count,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{os.getenv('GOOGLE_SHEET_ID')}"
    }


# ── Single daily run at 11:00 PM IST (5:30 PM UTC) ──────────────
@app.function(
    schedule=modal.Cron("30 17 * * *"),  # 23:00 IST = 17:30 UTC
    image=image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
    ],
    timeout=3600,
    memory=2048,
)
def nightly_run():
    """Nightly scheduled run — 11:00 PM IST every day."""
    return run_pipeline.local()


# ── Daily digest email at 8:00 AM IST (2:30 AM UTC) ─────────────
@app.function(
    schedule=modal.Cron("30 2 * * *"),  # 08:00 IST = 02:30 UTC
    image=image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
        modal.Secret.from_name("firebase-admin-key"),
    ],
    timeout=900,
)
def daily_digest():
    """Send each subscriber their personalized internship digest."""
    _setup_env()
    result = _run_script("execution/send_daily_digest.py", timeout=600)
    print(f"Digest run result: {result}")
    return {"status": "completed" if result == "success" else result}


# ── Webhook for manual triggers ─────────────────────────────
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
    ],
    timeout=3600,
    memory=2048,
)
@modal.fastapi_endpoint(method="GET")
def run_now():
    """Manual trigger via webhook."""
    result = run_pipeline.local()
    return result


# ── Health check ────────────────────────────────────────────
@app.function(image=image)
@modal.fastapi_endpoint(method="GET")
def health():
    """Health check endpoint"""
    return {"status": "healthy", "app": "internship-pipeline", "schedule": "daily 11PM IST"}


# ── Website API — replaces the now-dead Railway deployment ──────
@app.function(
    image=api_image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
    ],
    min_containers=1,  # keep one warm — this is public-facing, no cold starts
)
@modal.asgi_app()
def api_web():
    """Serves api/main.py's FastAPI app. Imports it lazily, after putting
    api/ on sys.path, because main.py's own top-level imports
    (`from sheets import ...`, `import email_service`) only resolve that way
    — see tests/test_main_asgi_import.py for the pinned assumption."""
    import sys
    if "/app/api" not in sys.path:
        sys.path.insert(0, "/app/api")
    from main import app as fastapi_app
    return fastapi_app


# ── Cheap uptime check — the whole reason this project exists is that
# the last outage went unnoticed because seed-data masked it. ──────────
@app.function(
    image=api_image,
    schedule=modal.Period(minutes=30),
)
def api_uptime_check():
    import time
    import httpx
    url = "https://dakshinjain187--internship-pipeline-api-web.modal.run/api/listings"

    # One retry before failing — a lone httpx.ReadTimeout is often just a
    # transient blip between two Modal containers, not a real outage. Still
    # raises (and pages) if the second attempt also fails, so a genuine
    # outage is never swallowed.
    last_err = None
    for attempt in range(2):
        try:
            resp = httpx.get(url, timeout=20, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            count = len(data) if isinstance(data, list) else 0
            if count == 0:
                print(f"⚠️  UPTIME CHECK: {url} returned 0 listings")
                raise RuntimeError(f"Uptime check got 0 listings from {url}")
            print(f"✅ UPTIME CHECK: {url} returned {count} listings")
            return
        except Exception as e:
            last_err = e
            if attempt == 0:
                print(f"⚠️  UPTIME CHECK attempt 1 failed ({e}) — retrying once...")
                time.sleep(5)

    print(f"❌ UPTIME CHECK FAILED after retry: {url} — {last_err}")
    raise last_err


@app.function(
    secrets=[
        modal.Secret.from_name("internship-secrets"),
    ]
)
def test_log():
    """Diagnostic function to verify cloud logging and secrets."""
    import os
    print("HELLO FROM MODAL CLOUD")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    print(f"GOOGLE_SHEET_ID: {sheet_id}")
    creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
    print(f"GOOGLE_CREDENTIALS_JSON loaded: {bool(creds)}")
    token = os.getenv("GOOGLE_TOKEN_JSON")
    print(f"GOOGLE_TOKEN_JSON loaded: {bool(token)}")
    if creds:
        print(f"Creds startswith {{: {creds.startswith('{')}")
    apify_token = os.getenv("APIFY_API_TOKEN")
    print(f"APIFY_API_TOKEN loaded: {bool(apify_token)}")
    if apify_token:
        print(f"✅ Modal is using token: {apify_token[:8]}...{apify_token[-4:]}")
    else:
        print("❌ APIFY_API_TOKEN IS MISSING IN CLOUD!")
    print("DONE TEST LOG")


if __name__ == "__main__":
    # Local testing
    with app.run():
        run_pipeline.remote()
