"""
run_pipeline.py
---------------
Master orchestrator script for the Internship Automation Pipeline.
Runs locally.

Flow:
1. Run Scrapers (LinkedIn Posts, Niche, Unstop, Notion, etc.)
2. Run Aggregation & Scoring
3. Publish to Google Sheets

Note: LinkedIn Jobs is EXCLUDED per user request.
"""

import os
import subprocess
import json
import time

def run_script(script_path, desc):
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
        # Run script using current python executable
        result = subprocess.run(["python", script_path], check=False)
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

def main():
    print("="*60)
    print("🚀 STARTING INTERNSHIP PIPELINE")
    print("="*60)
    
    # 0. CLEANUP (Nightly Maintenance)
    # Remove internships > 4 days old from Google Sheets
    run_script("execution/cleanup_sheets.py", "Cleanup Stale Internships (>4 days)")

    # 1. SCRAPERS
    # LinkedIn Posts (High Priority + LLM Analysis)
    run_script("execution/scrape_linkedin_posts.py", "Scrape LinkedIn Posts (with LLM)")
    
    # Niche Sites
    run_script("execution/scrape_niche_sites.py", "Scrape Niche Sites")
    
    # Unstop (Notion fallback or manual setup)
    run_script("execution/scrape_unstop.py", "Scrape Unstop")
    
    # Notion Manual Source
    run_script("execution/scrape_notion.py", "Scrape Notion (Manual Source)")
    
    # Company Careers
    run_script("execution/scrape_company_careers.py", "Scrape Company Careers")
    
    # Government Portals (Optional/Backup)
    run_script("execution/scrape_government.py", "Scrape Government Portals")
    
    # NOTE: LinkedIn Jobs removed per user request
    
    # 2. AGGREGATION
    print("\n\n" + "="*30)
    print("PHASE 2: AGGREGATION")
    print("="*30)
    if run_script("execution/aggregate_and_score.py", "Aggregate & Score Internships"):
        
        # 3. PUBLISHING
        print("\n\n" + "="*30)
        print("PHASE 3: PUBLISH")
        print("="*30)
        run_script("execution/publish_to_sheets.py", "Publish to Google Sheets")
    
    else:
        print("\n❌ Aggregation failed, skipping publish.")
    
    print("\n" + "="*60)
    print("🏁 PIPELINE EXECUTION COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
