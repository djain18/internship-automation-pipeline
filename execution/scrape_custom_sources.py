"""
scrape_custom_sources.py
------------------------
Scrapes specific LinkedIn Company Pages and Websites provided by the user.
Uses OpenAI (via llm_post_analyzer) for verification.

Sources:
1. LinkedIn Companies:
   - groundzerocommunity
   - job-shob
   - the-jus-anima
   - binternz
   - policysquarelistings

2. Websites:
   - opportunitytrack.in
   - ngobox.org

Output:
    .tmp/custom_run_clean.json
"""

import os
import json
import requests
import re
from bs4 import BeautifulSoup
from apify_client import ApifyClient
from dotenv import load_dotenv
from llm_post_analyzer import filter_posts_with_llm

load_dotenv()

# Configuration
TMP_DIR = ".tmp"
OUTPUT_FILE = os.path.join(TMP_DIR, "custom_run_clean.json")
LINKEDIN_ACTOR = "supreme_coder/linkedin-post"

LINKEDIN_URLS = [
    "https://www.linkedin.com/company/groundzerocommunity/",
    "https://www.linkedin.com/company/job-shob/",
    "https://www.linkedin.com/company/the-jus-anima/",
    "https://www.linkedin.com/company/binternz/",
    "https://www.linkedin.com/company/policysquarelistings/"
]

WEBSITES = [
    "https://www.opportunitytrack.in",
    "https://ngobox.org/index.php"
]

def ensure_tmp_dir():
    os.makedirs(TMP_DIR, exist_ok=True)

def scrape_linkedin_companies():
    """Scrape posts from LinkedIn Company Pages via Apify."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("❌ APIFY_API_TOKEN missing")
        return []

    print(f"🕵️ Scraping {len(LINKEDIN_URLS)} LinkedIn Company Pages...")
    client = ApifyClient(api_token)
    
    # Input for supreme_coder/linkedin-post
    # It accepts 'username' or 'url'. We pass full URLs.
    run_input = {
        "urls": LINKEDIN_URLS,
        "limitPerSource": 5, # Scrape recent 5 posts per company
        "deepScrape": True
    }
    
    try:
        run = client.actor(LINKEDIN_ACTOR).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"   ✅ Fetched {len(items)} posts from LinkedIn.")
        return items
    except Exception as e:
        print(f"   ❌ LinkedIn Scrape Error: {e}")
        return []

def scrape_website_simple(url):
    """Simple HTML scraper for websites."""
    print(f"🌍 Scraping website: {url}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Heuristic: Find potential internship/job blocks
        # 1. Look for 'article', 'div' with class 'post', 'job', etc.
        # For now, we'll be aggressive: Extract all paragraphs with links.
        
        posts = []
        # General extraction
        for tag in soup.find_all(['article', 'div', 'li']):
            text = tag.get_text(strip=True)
            if len(text) < 50 or len(text) > 3000:
                continue
            
            # Look for keywords
            if any(k in text.lower() for k in ['intern', 'hiring', 'opportunity', 'apply', 'vacancy', 'fellowship']):
                # Find link
                link = tag.find('a')
                href = link['href'] if link and link.has_attr('href') else url
                
                # Check duplication
                if any(p['text'] == text for p in posts):
                    continue
                    
                posts.append({
                    "text": text,
                    "url": href if href.startswith('http') else url + href,
                    "source": url,
                    "posted_time": "Today" # simplified
                })
                
        # Limit to top 10 per site to avoid spamming LLM
        print(f"   found {len(posts)} potential items from {url}")
        return posts[:10]
        
    except Exception as e:
        print(f"   ❌ Website Scrape Error ({url}): {e}")
        return []

def main():
    ensure_tmp_dir()
    
    all_raw_posts = []
    
    # 1. LinkedIn
    li_posts = scrape_linkedin_companies()
    for p in li_posts:
        # Normalize for LLM
        all_raw_posts.append({
            "text": p.get("text") or p.get("content") or "",
            "url": p.get("url") or p.get("postUrl") or "",
            "posted_time": p.get("postedDate") or p.get("postedAtISO") or "",
            "source": "LinkedIn Company"
        })
        
    # 2. Websites
    for site in WEBSITES:
        web_posts = scrape_website_simple(site)
        all_raw_posts.append(web_posts) # Append list? No, extend.
        
    # Fix list flattening if needed
    flat_posts = []
    for item in all_raw_posts:
        if isinstance(item, list):
            flat_posts.extend(item)
        else:
            flat_posts.append(item)
            
    print(f"\n📊 Total Items to Analyze: {len(flat_posts)}")
    if not flat_posts:
        print("No items found.")
        return

    # 3. LLM Verification (OpenAI)
    print("🤖 Verifying with OpenAI (gpt-4o-mini)...")
    verified = filter_posts_with_llm(flat_posts)
    
    # 4. Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(verified, f, indent=2)
        
    print(f"✅ Saved {len(verified)} verified items to {OUTPUT_FILE}")
    
    # 5. Publish
    if verified:
        import subprocess
        print("🚀 Publishing to Google Sheet...")
        subprocess.run(["python", "execution/publish_mnc_run.py", OUTPUT_FILE])

if __name__ == "__main__":
    main()
