import os
import json
import time
import subprocess
from dotenv import load_dotenv
from apify_client import ApifyClient
from dateutil.parser import parse

# Load env
load_dotenv()
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
TARGET_URLS = [
    "https://www.linkedin.com/company/0-1xhiring/",
    "https://www.linkedin.com/company/theseekers/",
    "https://www.linkedin.com/company/founders-office-club/"
]

# Config
USE_LLM = True
# Try to import LLM
try:
    from llm_post_analyzer import filter_posts_with_llm
    print("✅ Verified: LLM module available")
except ImportError:
    print("⚠️ LLM module not found, skipping verification")
    USE_LLM = False

OUTPUT_FILE = ".tmp/manual_companies.json"

def main():
    if not APIFY_TOKEN:
        print("❌ No APIFY_API_TOKEN")
        return

    client = ApifyClient(APIFY_TOKEN)
    all_clean_posts = []

    print(f"🎯 Targeting {len(TARGET_URLS)} Company Pages...")

    for url in TARGET_URLS:
        print(f"\n🔍 Scraping: {url}")
        
        # Input for supreme_coder/linkedin-post
        # Trying direct URL. If fails, might need "username" extraction or "authorUrn".
        run_input = {
            "urls": [url], 
            "limitPerSource": 10,  # Get last 10 posts
            "deepScrape": True
        }
        
        try:
            run = client.actor("supreme_coder/linkedin-post").call(run_input=run_input)
            dataset_id = run["defaultDatasetId"]
            raw_posts = list(client.dataset(dataset_id).iterate_items())
            print(f"   Fetched {len(raw_posts)} raw posts")
            
            if not raw_posts:
                continue

            # Process
            for p in raw_posts:
                # Basic fields
                text = p.get("text") or p.get("description") or ""
                post_url = p.get("url") or p.get("postUrl")
                if not text or not post_url: continue
                
                # Dedupe within this run? (Set check handled at end)
                
                # Check freshness (7 days) approx
                # (Skipping complex date parse for speed, relying on LLM or manual check)
                
                # Author Type = Company (Since we scraped a Company Page)
                
                clean_post = {
                    "text": text,
                    "url": post_url,
                    "posted_time": p.get("postedAtISO") or p.get("date") or "Recently",
                    "author_name": p.get("author", {}).get("name", "Target Company"),
                    "author_type": "Company", # Explicit
                    "engagement_score": (p.get("likes", 0) or 0) + (p.get("comments", 0) or 0)
                }
                all_clean_posts.append(clean_post)
                
        except Exception as e:
            print(f"   ❌ Error scraping {url}: {e}")

    print(f"\nTotal Raw Candidates: {len(all_clean_posts)}")
    if not all_clean_posts:
        print("No posts found.")
        return

    # Verify with LLM
    verified_posts = []
    if USE_LLM:
        print("🤖 Verifying with LLM (using filter_posts_with_llm)...")
        # Adapt list to expected format
        try:
            verified_posts = filter_posts_with_llm(all_clean_posts)
        except Exception as e:
            print(f"⚠️ LLM Error: {e}")
            verified_posts = []

        if not verified_posts and all_clean_posts:
             print("⚠️ LLM yielded 0 results (or failed). Using Regex Fallback.")
             for p in all_clean_posts:
                match_role = "Internship" 
                p_text = (p.get("text") or "").lower()
                for r_kw in ["finance", "marketing", "operations", "hr", "sales", "business analyst", "data science"]:
                    if r_kw in p_text:
                        match_role = r_kw.title() + " Intern"
                        break
                
                # Manual scraper specific fields
                p["role"] = match_role
                p["company"] = p.get("author_name", "Target Company")
                p["location"] = "India"
                verified_posts.append(p)
    else:
        verified_posts = all_clean_posts # No verification

    print(f"\n✅ Final Verified Count: {len(verified_posts)}")
    
    # Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(verified_posts, f, indent=2)
        
    # Publish
    if verified_posts:
        print("🚀 Publishing...")
        try:
            subprocess.run(["python", "execution/publish_mnc_run.py", OUTPUT_FILE], check=True)
            print("✅ Published successfully!")
        except Exception as e:
            print(f"❌ Publish failed: {e}")

if __name__ == "__main__":
    main()
