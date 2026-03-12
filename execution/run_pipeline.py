"""
run_pipeline.py
----------------
Master orchestrator that runs the complete internship pipeline.

Usage:
    python execution/run_pipeline.py              # Run all sources
    python execution/run_pipeline.py --quick      # Run LinkedIn only (faster)
    python execution/run_pipeline.py --test       # Dry run, no API calls

This script:
1. Runs all source scrapers in priority order
2. Aggregates and scores results
3. Publishes to Google Sheets
4. Logs execution summary
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Constants
TMP_DIR = ".tmp"
LOG_FILE = os.path.join(TMP_DIR, "pipeline_log.json")

# Scraper scripts in priority order
SCRAPERS = [
    {"name": "LinkedIn Posts", "script": "scrape_linkedin_posts.py", "priority": 1},
    {"name": "LinkedIn Jobs", "script": "scrape_linkedin_jobs.py", "priority": 2},
    {"name": "Niche Sites", "script": "scrape_niche_sites.py", "priority": 3},
    {"name": "Unstop", "script": "scrape_unstop.py", "priority": 4},
    {"name": "Government", "script": "scrape_government.py", "priority": 6},
]


def ensure_tmp_dir():
    os.makedirs(TMP_DIR, exist_ok=True)


def run_script(script_name: str) -> dict:
    """Run a scraper script and return result."""
    script_path = os.path.join("execution", script_name)
    
    if not os.path.exists(script_path):
        return {"status": "skipped", "error": "Script not found", "count": 0}
    
    start_time = time.time()
    
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        result = subprocess.run(
            [sys.executable, script_path],
            timeout=1200,  # 20 minute timeout per scraper
            env=env
        )
        
        elapsed = time.time() - start_time
        
        # Note: count extraction is skipped when stdout is not captured 
        # (done to allow real-time streaming in Modal/CLI)
        count = 0
        
        return {
            "status": "success" if result.returncode == 0 else "failed",
            "elapsed_seconds": round(float(elapsed), 1),
            "count": count,
            "error": "Script failed with exit code " + str(result.returncode) if result.returncode != 0 else None
        }
        
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "Script exceeded 20 minute timeout", "count": 0}
    except Exception as e:
        return {"status": "error", "error": str(e), "count": 0}


def run_aggregation() -> dict:
    """Run aggregation and scoring."""
    return run_script("aggregate_and_score.py")


def run_publish() -> dict:
    """Run Google Sheets publish."""
    return run_script("publish_to_sheets.py")


def load_final_count() -> int:
    """Load count from final ranked file."""
    final_file = os.path.join(TMP_DIR, "final_ranked_internships.json")
    if os.path.exists(final_file):
        try:
            data = json.load(open(final_file, encoding='utf-8'))
            return len(data)
        except:
            pass
    return 0


def save_log(log_entry: dict):
    """Append to pipeline log."""
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            logs = json.load(open(LOG_FILE, encoding='utf-8'))
        except:
            pass
    
    logs.append(log_entry)
    
    # Keep last 100 logs
    logs = logs[-100:]
    
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=2)


def main(quick_mode: bool = False, test_mode: bool = False):
    """Run the complete pipeline."""
    ensure_tmp_dir()
    
    print("=" * 60)
    print("INTERNSHIP PIPELINE - MASTER ORCHESTRATOR")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    if test_mode:
        print("\n[TEST MODE] No API calls will be made\n")
        return
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "mode": "quick" if quick_mode else "full",
        "scrapers": {},
        "total_internships": 0,
        "status": "running"
    }
    
    # Phase 1: Run scrapers
    print("\n[PHASE 1] Running Scrapers")
    print("-" * 40)
    
    scrapers_to_run = SCRAPERS[:2] if quick_mode else SCRAPERS
    
    total_count = 0
    for scraper in scrapers_to_run:
        print(f"\n>> {scraper['name']}...")
        result = run_script(scraper['script'])
        log_entry["scrapers"][scraper['name']] = result
        total_count += result.get('count', 0)
        
        status_icon = "OK" if result['status'] == 'success' else "FAIL"
        print(f"   [{status_icon}] {result.get('count', 0)} items in {result.get('elapsed_seconds', 0)}s")
        
        if result.get('error'):
            print(f"   Error: {result['error'][:100]}")
    
    # Phase 2: Aggregate and Score
    print("\n[PHASE 2] Aggregating and Scoring")
    print("-" * 40)
    
    agg_result = run_aggregation()
    log_entry["aggregation"] = agg_result
    print(f"   [{agg_result['status'].upper()}] in {agg_result.get('elapsed_seconds', 0)}s")
    
    final_count = load_final_count()
    log_entry["total_internships"] = final_count
    
    # Phase 3: Publish to Google Sheets
    print("\n[PHASE 3] Publishing to Google Sheets")
    print("-" * 40)
    
    if os.getenv("GOOGLE_SHEET_ID"):
        pub_result = run_publish()
        log_entry["publish"] = pub_result
        print(f"   [{pub_result['status'].upper()}] in {pub_result.get('elapsed_seconds', 0)}s")
    else:
        print("   [SKIPPED] GOOGLE_SHEET_ID not set")
        log_entry["publish"] = {"status": "skipped", "error": "GOOGLE_SHEET_ID not set"}
    
    # Summary
    log_entry["status"] = "completed"
    save_log(log_entry)
    
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Total Internships: {final_count}")
    print(f"Log saved: {LOG_FILE}")
    
    if os.getenv("GOOGLE_SHEET_ID"):
        print(f"Sheet: https://docs.google.com/spreadsheets/d/{os.getenv('GOOGLE_SHEET_ID')}")
    
    return final_count


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    test = "--test" in sys.argv
    main(quick_mode=quick, test_mode=test)
