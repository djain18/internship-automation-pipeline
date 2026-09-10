"""
run_pipeline.py
---------------
Master orchestrator script for the Internship Automation Pipeline.
Runs locally and is also triggered identically by Modal for cloud runs.

Flow:
1. Run Scraper: LinkedIn Posts (Scraping + LLM filtering mapping directly to JSON)
2. Stage Output: Bypasses the multi-source aggregator as per user request (LinkedIn only)
3. Publish: Google Sheets & FTB API

"""

import json
import os
import subprocess
import shutil
import sys
import time

# Force UTF-8 stdout/stderr so emoji log lines don't crash local Windows runs
# (cp1252 console). Linux/Modal already default to UTF-8; this is a no-op there.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

def run_script(script_path, desc, timeout=3400):
    """Run a python script and wait for it to complete."""
    print(f"\n{'-'*60}")
    print(f"STEP: {desc}")
    print(f"SCRIPT: {script_path}")
    print(f"{'-'*60}")
    
    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return False
    
    start_time = time.time()
    try:
        # Run script using current environment python
        import sys
        result = subprocess.run([sys.executable, script_path], check=False, timeout=timeout)
        duration = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✅ {desc} completed in {duration:.1f}s")
            return True
        else:
            print(f"❌ {desc} FAILED (Exit Code: {result.returncode})")
            return False
            
    except Exception as e:
        print(f"❌ Error running {desc}: {e}")
        return False

# Quality-first policy (2026-07): there is NO hard quota. TARGET_NEW is a SOFT
# target — we stop early once reached, and we NEVER pad with low-quality posts to
# hit it. Topup passes exist only to gather genuine posts we may have missed; a
# pass that yields few net-new means the genuine supply is exhausted, so we stop.
# 45, not 35: role_taxonomy.balance now spreads output across 12 role tracks
# (quota 5 each), so the ceiling a healthy night can reach is much higher than
# when one oversupplied field was doing all the work. Still SOFT — balance
# never pads, so a thin night simply publishes fewer.
TARGET_NEW = 45    # soft target; publishing fewer genuine ones is acceptable
MAX_RETRIES = 1    # at most one topup pass; quality over volume
MIN_MARGINAL_YIELD = 8  # stop topup if a pass adds fewer than this (supply dry)


def _read_publish_result():
    """Read how many entries were appended in the last publish step."""
    result_file = ".tmp/publish_result.json"
    if os.path.exists(result_file):
        try:
            with open(result_file) as f:
                return json.load(f).get("appended", 0)
        except Exception:
            pass
    return 0


def _write_topup_config(deficit):
    """Tell the scraper to run in topup mode targeting `deficit` extra posts."""
    with open(".tmp/scrape_topup.json", "w") as f:
        json.dump({"target": deficit + 15}, f)  # +15 buffer for filter losses


def _clear_topup_config():
    if os.path.exists(".tmp/scrape_topup.json"):
        os.remove(".tmp/scrape_topup.json")


def run_scrape_and_publish():
    """Run one scrape → stage → publish cycle. Returns count of new entries appended."""
    linkedin_output = ".tmp/linkedin_posts_clean.json"
    final_output = ".tmp/final_ranked_internships.json"

    if not run_script("execution/scrape_linkedin_posts.py", "Scrape LinkedIn Posts (with LLM Extraction)"):
        return 0

    if not os.path.exists(linkedin_output):
        print(f"❌ No valid {linkedin_output} found.")
        return 0

    shutil.copy(linkedin_output, final_output)
    print(f"✅ LinkedIn data staged as final output.")

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if sheet_id or os.path.exists(".env"):
        run_script("execution/publish_to_sheets.py", "Publish to Google Sheets & FTB API")
    else:
        print("⚠️ Skipping publishing — no GOOGLE_SHEET_ID detected.")

    return _read_publish_result()


def main():
    print("="*60)
    print("STARTING UNIFIED INTERNSHIP PIPELINE (LINKEDIN ONLY)")
    print("="*60)

    os.makedirs(".tmp", exist_ok=True)
    _clear_topup_config()

    # --- PHASE 0: Export existing sheet keys so scraper avoids known internships ---
    print("\n\n" + "="*30)
    print("PHASE 0: EXPORT EXISTING SHEET KEYS")
    print("="*30)
    run_script("execution/export_sheet_keys.py", "Export Existing Sheet Dedup Keys")

    # --- PHASE 1+2+3: Scrape → Stage → Publish (with retry loop) ---
    total_appended = 0

    for attempt in range(1, MAX_RETRIES + 2):  # attempts: 1, 2, 3
        print("\n\n" + "="*30)
        print(f"SCRAPE + PUBLISH ATTEMPT {attempt}/{MAX_RETRIES + 1}")
        print("="*30)

        appended = run_scrape_and_publish()
        total_appended += appended
        print(f"\n>>> Attempt {attempt} result: {appended} new genuine entries published (total so far: {total_appended}, soft target {TARGET_NEW})")

        if total_appended >= TARGET_NEW:
            print(f"✅ Soft target of {TARGET_NEW} reached — stopping (quality-first).")
            break

        # Quality-first early stop: if this pass barely added anything, the pool
        # of genuine Bengaluru/remote internships is exhausted. Padding further
        # only reintroduces spam, so stop here and publish what we have.
        if attempt > 1 and appended < MIN_MARGINAL_YIELD:
            print(f"🟢 Only {appended} net-new this pass (< {MIN_MARGINAL_YIELD}). "
                  f"Genuine supply looks exhausted — stopping with {total_appended} quality internships.")
            break

        if attempt <= MAX_RETRIES:
            deficit = TARGET_NEW - total_appended
            print(f"\n↻ {total_appended} published so far. Running one topup pass for up to {deficit} more genuine posts...")
            # Refresh sheet keys (now includes the rows just appended)
            run_script("execution/export_sheet_keys.py", "Refresh Sheet Dedup Keys for Topup")
            _write_topup_config(deficit)
        else:
            print(f"🟢 Done. Final count: {total_appended} genuine internships published (no padding).")

    _clear_topup_config()

    print("\n" + "="*60)
    print("PIPELINE EXECUTION COMPLETE")
    print(f"LinkedIn: {total_appended} published")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"🛑 CRITICAL PIPELINE ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
