"""
custom_run_founders_ai.py
-------------------------
Custom execution script to scrape internships matching:
- High priority roles: Founder's Office, Chief of Staff, AI Automation, AI Engineer, ML
- Location constraint: Remote OR Chennai ONLY.

Uses Apify actor 'supreme_coder/linkedin-post' and Gemini 2.5 Flash-lite via defined API Key.
Publishes to a brand new Google Sheet.
"""

import os
import sys
import json
import re
import time
from datetime import datetime

# Inject user-specified AI key
# Note: Gemini hit quota limit, using existing Groq integration Instead
# os.environ["GEMINI_API_KEY"] = "your_gemini_api_key_here"

# Add project root to python path so we can import internal modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from apify_client import ApifyClient
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import google.generativeai as genai

# Internal Tools
import execution.llm_post_analyzer as llm
import execution.publish_to_sheets as pub_utils

# Use the LLM framework's configured provider, which will be Groq since we 
# aren't force-feeding Gemini
llm.configure_llm()
print(f"Using Provider: {llm.PROVIDER}")

# Config
TARGET_COUNT = 130
ACTOR_ID = "supreme_coder/linkedin-post"
TMP_DIR = ".tmp"
os.makedirs(TMP_DIR, exist_ok=True)
RAW_FILE = os.path.join(TMP_DIR, "founders_ai_raw.json")
CLEAN_FILE = os.path.join(TMP_DIR, "founders_ai_clean.json")

# Keywords
SEARCH_QUERIES = [
    # Chennai Onsite Focus - High Intent
    '("founder\'s office" OR "chief of staff") AND (hiring OR recruitment OR opportunity OR "apply") AND (chennai)',
    '("ai automation" OR "ai engineer" OR "machine learning") AND (hiring OR recruitment OR opportunity OR "apply") AND (chennai)',
    'hiring "founder\'s office intern" chennai',
    'hiring "ai automation intern" chennai',
    # Remote/India Focus - High Intent
    '("founder\'s office" OR "chief of staff") AND (hiring OR recruitment OR opportunity OR "apply") AND (india OR remote)',
    '("ai automation" OR "ai engineer" OR "machine learning") AND (hiring OR recruitment OR opportunity OR "apply") AND (india OR remote)',
    'hiring "founder\'s office intern" remote',
    'hiring "ai automation intern" remote',
]

def run_apify_search(query: str, limit: int = 50) -> list:
    """Run Apify actor for a given query."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not found in .env")
        return []
        
    client = ApifyClient(api_token)
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
    """Filter for Chennai, India, or Remote ONLY"""
    loc_lower = (location or "").lower()
    text_lower = (post_text or "").lower()
    
    # Exclude common foreign locations
    foreign_keywords = [
        "usa", "uk", "united states", "united kingdom", "canada", "australia",
        "germany", "france", "europe", "dubai", "uae", "singapore", "malaysia",
        "london", "new york", "san francisco", "california", "texas", "amsterdam",
        "remote us", "remote uk", "us only"
    ]
    for fw in foreign_keywords:
        if re.search(r'\b' + fw + r'\b', loc_lower):
            return False
            
    # Check if explicitly Chennai or India
    if "chennai" in loc_lower or "chennai" in text_lower or "india" in loc_lower or "india" in text_lower:
        return True
        
    # Check if explicitly Remote/WFH
    if ("remote" in loc_lower or "work from home" in loc_lower or "wfh" in loc_lower or
        "remote" in text_lower or "work from home" in text_lower or "wfh" in text_lower):
        return True
    
    return False

def scrape_and_process():
    verified_posts = []
    seen_urls = set()
    
    print(f"Using LLM Provider: {llm.PROVIDER} | Model: {llm.MODEL}")
    
    for query in SEARCH_QUERIES:
        if len(verified_posts) >= TARGET_COUNT:
            break
            
        raw_items = run_apify_search(query, 100)
        
        # Initial Dedup
        unique_items = []
        for p in raw_items:
            url = p.get("url") or p.get("postUrl")
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
                
            clean_record = {
                "title": role,
                "role": role,  # needed for backwards compatibility
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
                "company": company, # backwards compat
                "author_name": post.get("authorName", ""),
                "url": post.get("url", ""),
                "apply_link": analysis.get("apply_link", ""),
                "contact_email": analysis.get("contact_email", ""),
                
                # Prioritization Score: Founder's Office or AI Automation gets a boost
                "engagement_score": 5 if any(x in (role + company).lower() for x in ["founder", "office", "ai", "automation", "chief"]) else 1,
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

def publish_to_existing_sheet(items):
    """Appends data to the existing Founders custom sheet with specific 'Human' headers."""
    if not items:
        print("No items to publish.")
        return
        
    print("\nConnecting to Google Sheets via OAuth...")
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pub_utils.CREDENTIALS_FILE = os.path.join(root_dir, "credentials.json")
    pub_utils.TOKEN_FILE = os.path.join(root_dir, "token.json")
    
    try:
        service = pub_utils.get_sheets_service()
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return
    
    sheet_id = "1SI28rbwXo2N063_94ftp3biqNrmjVio0Xp3SXEix3WE"
    sheet_name = "Sheet1"
    
    # 1. Custom Headers requested by User
    CUSTOM_HEADERS = [
        "Title", "Type", "Timing", "Description", "Stipend", "Duration", 
        "Experience", "Location", "Deadline", "Tags", "HiringOrganization", 
        "HiringManager", "Post URL", "Apply Link", "Contact Email", "Date Added"
    ]
    
    # 2. Ensure Headers exist
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A1:P1",
        valueInputOption="RAW",
        body={"values": [CUSTOM_HEADERS]}
    ).execute()
    
    # 3. Clear existing data below headers (A2:P5000)
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A2:P5000"
    ).execute()
    
    # 4. Map items to custom rows
    new_rows = []
    for item in items:
        tags_raw = item.get("tags", "")
        tags_str = ", ".join(str(t) for t in tags_raw) if isinstance(tags_raw, list) else str(tags_raw)
        
        new_rows.append([
            item.get("role", ""),              # Title
            "Internship",                      # Type
            item.get("timing", "Full-time"),    # Timing
            item.get("description", ""),        # Description (Whole post)
            item.get("stipend", "Unpaid"),      # Stipend
            item.get("duration", "3-6 months"), # Duration
            item.get("experience", "Fresher"),  # Experience
            item.get("location", ""),           # Location
            item.get("deadline", "N/A"),        # Deadline
            tags_str,                           # Tags
            item.get("company", ""),            # HiringOrganization
            item.get("author_name", "N/A"),     # HiringManager
            item.get("url", ""),                # Post URL
            item.get("apply_link", ""),         # Apply Link
            item.get("contact_email", ""),       # Contact Email
            datetime.now().strftime("%Y-%m-%d") # Date Added
        ])
        
    # 5. Append new rows
    if new_rows:
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A2",
            valueInputOption="RAW",
            body={"values": new_rows}
        ).execute()
        print(f"✅ Appended {len(new_rows)} fresh internships with custom mapping.")

    print(f"\n" + "="*50)
    print(f"✅ SUCCESS! Specialized sheet is now structured for Humans.")
    print(f"🔗 URL: https://docs.google.com/spreadsheets/d/{sheet_id}")
    print("="*50)

if __name__ == "__main__":
    print("🚀 Starting Professional Human-Centric Run")
    if os.path.exists(CLEAN_FILE):
        with open(CLEAN_FILE, 'r', encoding='utf-8') as f:
            items = json.load(f)
        print(f"Loaded {len(items)} verified items from cache.")
        publish_to_existing_sheet(items)
    else:
        items = scrape_and_process()
        publish_to_existing_sheet(items)
