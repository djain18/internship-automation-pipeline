"""
modal_app.py
-------------
Modal serverless deployment for the Internship Pipeline.

Features:
- Scheduled cron job (daily 9PM IST = 3:30PM UTC)
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
        "google-generativeai",
        "groq",
        "openai",
        "python-dateutil",
    )
    .add_local_dir("execution", remote_path="/app/execution")
)


def _setup_env():
    """Common setup: create credential files from Modal secrets."""
    os.chdir("/app")
    os.makedirs(".tmp", exist_ok=True)
    
    if os.getenv("GOOGLE_CREDENTIALS_JSON"):
        with open("credentials.json", "w") as f:
            f.write(os.getenv("GOOGLE_CREDENTIALS_JSON"))
    
    if os.getenv("GOOGLE_TOKEN_JSON"):
        with open("token.json", "w") as f:
            f.write(os.getenv("GOOGLE_TOKEN_JSON"))


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
    secrets=[modal.Secret.from_name("internship-secrets")],
    timeout=2400,  # 40 minutes max (130 posts takes ~20 mins)
)
def run_pipeline():
    """
    Run the full internship pipeline:
    1. Scrape LinkedIn Posts (target: 130)
    2. Aggregate & Score
    3. Publish to Google Sheets
    4. Push to FTB Hustle API
    """
    _setup_env()
    
    print("=" * 60)
    print("INTERNSHIP PIPELINE - MODAL EXECUTION")
    print("Target: 130 India-only Internships")
    print("=" * 60)
    
    results = {}
    
    # Step 1: Scrape LinkedIn Posts
    results["scrape"] = _run_script("execution/scrape_linkedin_posts.py", timeout=1200)
    
    # Step 2: Aggregate & Score
    results["aggregate"] = _run_script("execution/aggregate_and_score.py", timeout=180)
    
    # Step 3: Publish to Google Sheets + API
    if os.getenv("GOOGLE_SHEET_ID"):
        results["publish"] = _run_script("execution/publish_to_sheets.py", timeout=180)
    else:
        print("\n>> Step 3: Skipped (GOOGLE_SHEET_ID missing)")
        results["publish"] = "skipped"
    
    # Final count
    final_count = 0
    if os.path.exists(".tmp/final_ranked_internships.json"):
        try:
            with open(".tmp/final_ranked_internships.json") as f:
                final_count = len(json.load(f))
        except Exception:
            pass
    
    print(f"\n{'=' * 60}")
    print(f"COMPLETE — {final_count} internships extracted")
    print(f"Push results: {results}")
    print('=' * 60)
    
    return {
        "status": "completed",
        "internships_count": final_count,
        "results": results,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{os.getenv('GOOGLE_SHEET_ID')}"
    }


# ── Single daily run at 9:00 PM IST (3:30 PM UTC) ──────────────
@app.function(
    schedule=modal.Cron("30 15 * * *"),  # 9:00 PM IST = 15:30 UTC
    image=image,
    secrets=[modal.Secret.from_name("internship-secrets")],
    timeout=2400,
)
def nightly_run():
    """Nightly scheduled run — 9:00 PM IST every day."""
    return run_pipeline.local()


# ── Webhook for manual triggers ─────────────────────────────
@app.function(
    image=image,
    secrets=[modal.Secret.from_name("internship-secrets")],
    timeout=2400,
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
    return {"status": "healthy", "app": "internship-pipeline", "schedule": "daily 9PM IST"}


@app.function()
def test_log():
    """Diagnostic function to verify cloud logging."""
    print("HELLO FROM MODAL CLOUD")
    import time
    for i in range(5):
        print(f"Log count: {i}", flush=True)
        time.sleep(1)
    print("DONE TEST LOG")


if __name__ == "__main__":
    # Local testing
    with app.run():
        run_pipeline.remote()
