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
        "python-dateutil",
    )
    .add_local_dir("execution", remote_path="/app/execution")
    .add_local_file("run_pipeline.py", remote_path="/app/run_pipeline.py")
    .add_local_file("extraction_prompt.txt", remote_path="/app/extraction_prompt.txt")
    .add_local_file("token.json", remote_path="/app/token.json") 
)


def _setup_env():
    """Common setup: create credential files from Modal secrets."""
    os.chdir("/app")
    os.makedirs(".tmp", exist_ok=True)
    
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
