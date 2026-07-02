"""
remote_founders_run.py
-------------------------
Custom execution script to scrape internships matching:
- High priority roles: Founder's Office, Chief of Staff, AI Automation, Generalist
- Location constraint: Remote ONLY.

Uses Apify actor 'supreme_coder/linkedin-post' and LLM post analyzer.
Publishes to a brand new Google Sheet.
"""

import os
import sys
import json
import re
from datetime import datetime

# Add project root to python path so we can import internal modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from apify_client import ApifyClient
import execution.llm_post_analyzer as llm
import execution.publish_to_sheets as pub_utils
import execution.format_google_sheet as formatter

# Initialize LLM
llm.configure_llm()
print(f"Using Provider: {llm.PROVIDER}")

# Config
TARGET_COUNT = 25  # exactly 25 as requested
ACTOR_ID = "supreme_coder/linkedin-post"
TMP_DIR = ".tmp"
os.makedirs(TMP_DIR, exist_ok=True)
CLEAN_FILE = os.path.join(TMP_DIR, "remote_founders_ai_clean.json")

# Keywords focusing on Remote, Founder's Office, Generalist, AI Automation
SEARCH_QUERIES = [
    '("founder\'s office" OR "chief of staff" OR generalist) AND (intern OR internship) AND remote',
    '("ai automation" OR "ai engineer") AND (intern OR internship) AND remote',
    'hiring "founder\'s office intern" remote',
    'hiring "generalist intern" remote',
    'hiring "ai automation intern" remote',
]

def run_apify_search(query: str, limit: int = 50) -> list:
    """Run Apify actor for a given query."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not found in .env")
        return []
        
    client = ApifyClient(api_token)
    # searching past-week to better match "not more than 5 days" timeframe
    search_url = f"https://www.linkedin.com/search/results/content/?datePosted=%22past-week%22&keywords={query.replace(' ', '%20')}&origin=FACETED_SEARCH"
    
    print(f"\nScraping LinkedIn Posts for query: {query}")
    try:
        run = client.actor(ACTOR_ID).call(run_input={"urls": [search_url], "limitPerSource": limit})
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f" > Retrieved {len(items)} raw posts")
        return items
    except Exception as e:
        print(f" > Apify error: {e}")
        return []

def filter_location(location: str, post_text: str) -> bool:
    """Filter for Remote ONLY"""
    loc_lower = (location or "").lower()
    text_lower = (post_text or "").lower()
    
    # Check if explicitly Remote/WFH
    if ("remote" in loc_lower or "work from home" in loc_lower or "wfh" in loc_lower or
        "remote" in text_lower or "work from home" in text_lower or "wfh" in text_lower):
        
        # Exclude if it explicitly says no remote
        if "no remote" in text_lower or "not remote" in text_lower:
            return False
            
        return True
    
    return False

def scrape_and_process():
    verified_posts = []
    seen_urls = set()
    seen_roles = set()
    
    for query in SEARCH_QUERIES:
        if len(verified_posts) >= TARGET_COUNT:
            break
            
        raw_items = run_apify_search(query, 100)
        
        # Initial Dedup
        unique_items = []
        for p in raw_items:
            url = p.get("url") or p.get("postUrl") or p.get("link")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_items.append(p)
                
        if not unique_items: 
            continue
        
        print(f"   Analyzing {len(unique_items)} unique items with LLM...")
        llm_results = llm.filter_posts_with_llm(unique_items)
        
        for post in llm_results:
            analysis = post.get("llm_analysis", {})
            if isinstance(analysis, list): analysis = analysis[0] if analysis else {}
            
            # Reconstruct basic required fields
            company = analysis.get("company", "")
            roles = analysis.get("roles", [])
            role = roles[0] if roles else "Internship"
            location = analysis.get("location", "Unknown")
            post_text = post.get("text", "")[:5000]
            
            # Apply STRICT location filter
            if not filter_location(location, post_text):
                continue
                
            role_key = f"{role.lower().strip()}_{company.lower().strip()}"
            if role_key in seen_roles:
                print(f"     ♻️ Skipped Duplicate Role: {role} @ {company}")
                continue
            seen_roles.add(role_key)
                
            clean_record = {
                "title": role,
                "role": role,
                "type": analysis.get("type", ""),
                "timing": analysis.get("timing", ""),
                "description": post_text,
                "stipend": analysis.get("stipend", ""),
                "duration": analysis.get("duration", ""),
                "experience": analysis.get("experience", ""),
                "location": location,
                "deadline": analysis.get("deadline", ""),
                "tags": analysis.get("tags", []),
                "hiringOrganization": company,
                "company": company,
                "author_name": post.get("authorName", "") or post.get("author", {}).get("name", "N/A"),
                "url": post.get("url", "") or post.get("postUrl", ""),
                "apply_link": analysis.get("apply_link", ""),
                "contact_email": analysis.get("contact_email", ""),
                
                "engagement_score": 5 if any(x in (role + company).lower() for x in ["founder", "office", "ai", "automation", "chief", "generalist"]) else 1,
                "is_stale": False,
                "freshness_bonus": 1
            }
            verified_posts.append(clean_record)
            print(f"     ✅ Kept: {role} @ {company} | Loc: {location}")
            
            if len(verified_posts) >= TARGET_COUNT:
                break
                
    with open(CLEAN_FILE, "w", encoding="utf-8") as f:
        json.dump(verified_posts, f, indent=2)
        
    print(f"\nFinal Verified Count: {len(verified_posts)}")
    return verified_posts

def create_fresh_sheet_and_publish(items):
    print("Creating a fresh Google Spreadsheet...")
    service = pub_utils.get_sheets_service()
    
    # 1. Create Spreadsheet
    title = f"Remote Focus: Founders Office & Generalist & AI ({datetime.now().strftime('%b %d, %Y')})"
    spreadsheet = {
        'properties': {'title': title}
    }
    spreadsheet = service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
    new_sheet_id = spreadsheet.get('spreadsheetId')
    print(f"✅ Created new sheet: {new_sheet_id}")

    # 2. Publish Data
    CUSTOM_HEADERS = [
        "Title", "Type", "Timing", "Description", "Stipend", "Duration", 
        "Experience", "Location", "Deadline", "Tags", "HiringOrganization", 
        "HiringManager", "Post URL", "Apply Link", "Contact Email", "Date Added"
    ]
    
    new_rows = []
    for item in items:
        new_rows.append([
            item.get("role", ""),              
            "Internship",                      
            item.get("timing", "Full-time"),    
            item.get("description", ""),        
            item.get("stipend", "Unpaid"),      
            item.get("duration", "3-6 months"), 
            item.get("experience", "Fresher"),  
            item.get("location", ""),           
            item.get("deadline", "N/A"),        
            ", ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else item.get("tags", ""), 
            item.get("company", ""),            
            item.get("author_name", "N/A"),     
            item.get("url", ""),                
            item.get("apply_link", ""),         
            item.get("contact_email", ""),       
            datetime.now().strftime("%Y-%m-%d") 
        ])

    # Update Headers
    service.spreadsheets().values().update(
        spreadsheetId=new_sheet_id,
        range="Sheet1!A1:P1",
        valueInputOption="RAW",
        body={"values": [CUSTOM_HEADERS]}
    ).execute()
    
    # Append Data
    if new_rows:
        service.spreadsheets().values().append(
            spreadsheetId=new_sheet_id,
            range="Sheet1!A2",
            valueInputOption="RAW",
            body={"values": new_rows}
        ).execute()
        print(f"✅ Appended {len(new_rows)} items to the fresh sheet.")

    # 3. Format Sheet
    try:
        formatter.apply_formatting(new_sheet_id)
    except Exception as e:
        print(f"Warning: Could not fully format sheet: {e}")
    
    print("\n" + "="*50)
    print("✨ ALL DONE! Fresh Sheet Ready.")
    print(f"🔗 URL: https://docs.google.com/spreadsheets/d/{new_sheet_id}")
    print("="*50)

if __name__ == "__main__":
    print("🚀 Starting Remote-Only Founder's/Generalist/AI Run")
    # Always scrape fresh on new invocation
    items = scrape_and_process()
    if items:
        create_fresh_sheet_and_publish(items)
    else:
        print("No items found to publish.")
