"""
scrape_notion.py
-----------------
Scrapes internships from a Notion Database using the official API.
Requires NOTION_TOKEN and NOTION_DATABASE_ID in .env.

Output:
    .tmp/notion_clean.json
"""

import os
import json
from notion_client import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
TMP_DIR = ".tmp"
CLEAN_OUTPUT = os.path.join(TMP_DIR, "notion_clean.json")

def ensure_tmp_dir():
    os.makedirs(TMP_DIR, exist_ok=True)

def fetch_from_notion():
    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_DATABASE_ID")

    if not token or not db_id:
        print("Missing NOTION_TOKEN or NOTION_DATABASE_ID in .env")
        return []

    print(f"Querying Notion Database: {db_id}...")
    notion = Client(auth=token)

    results = []
    has_more = True
    next_cursor = None

    try:
        while has_more:
            response = notion.databases.query(
                database_id=db_id,
                start_cursor=next_cursor,
                page_size=100,
                # Optional: Filter for Status != Closed if you have such a property
                # filter={"property": "Status", "select": {"does_not_equal": "Closed"}}
            )
            
            for page in response["results"]:
                props = page["properties"]
                
                # Extract Title
                title_prop = props.get("Title") or props.get("Role") or props.get("Name")
                title = ""
                if title_prop and title_prop["type"] == "title" and title_prop["title"]:
                    title = title_prop["title"][0]["plain_text"]
                elif title_prop and title_prop["type"] == "rich_text" and title_prop["rich_text"]:
                    title = title_prop["rich_text"][0]["plain_text"]
                    
                # Extract URL
                url_prop = props.get("URL") or props.get("Link") or props.get("Apply Link")
                link = ""
                if url_prop and url_prop["type"] == "url":
                    link = url_prop["url"]
                
                # Extract Company
                company_prop = props.get("Company")
                company = "Notion Entry"
                if company_prop and company_prop["type"] == "select" and company_prop["select"]:
                    company = company_prop["select"]["name"]
                elif company_prop and company_prop["type"] == "rich_text" and company_prop["rich_text"]:
                     company = company_prop["rich_text"][0]["plain_text"]

                # Extract Location
                loc_prop = props.get("Location")
                location = "India"
                if loc_prop and loc_prop["type"] == "select" and loc_prop["select"]:
                    location = loc_prop["select"]["name"]
                elif loc_prop and loc_prop["type"] == "rich_text" and loc_prop["rich_text"]:
                    location = loc_prop["rich_text"][0]["plain_text"]

                if title and link:
                    results.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": link,
                        "source": "Notion (Manual)",
                        "score_bonus": 20  # Bonus for manual verification
                    })
            
            has_more = response.get("has_more")
            next_cursor = response.get("next_cursor")
            
        print(f"Fetched {len(results)} internships from Notion.")
        return results

    except Exception as e:
        print(f"Notion API Error: {e}")
        return []

def fetch_page_content(page_id):
    """Fetches text content from a specific Notion Page."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return ""
        
    client = Client(auth=token)
    try:
        blocks = client.blocks.children.list(block_id=page_id)
        text_content = ""
        for block in blocks["results"]:
            if block["type"] == "paragraph":
                text = block["paragraph"]["rich_text"]
                if text:
                    text_content += text[0]["plain_text"] + "\n"
            elif block["type"] == "heading_1":
                text = block["heading_1"]["rich_text"]
                if text:
                    text_content += "\n# " + text[0]["plain_text"] + "\n"
            # Add other types as needed
        return text_content
    except Exception as e:
        print(f"Error fetching page {page_id}: {e}")
        return ""

def process_whatsapp_dump_page():
    """Checks for a specialized 'WhatsApp Dump' page if configured."""
    page_id = os.getenv("NOTION_DUMP_PAGE_ID")
    if not page_id:
        return []
        
    print(f"📄 Fetching content from Notion Dump Page: {page_id}...")
    raw_text = fetch_page_content(page_id)
    if not raw_text:
        print("   No content found.")
        return []
        
    print(f"   Fetched {len(raw_text)} chars. Parsing...")
    
    # Use existing parse_whatsapp logic (we need to import it or duplicate it)
    # Better to import.
    try:
        from parse_whatsapp import parse_chat_log
        from llm_post_analyzer import filter_posts_with_llm
        
        messages = parse_chat_log(raw_text)
        print(f"   Parsed {len(messages)} messages.")
        
        verified = filter_posts_with_llm(messages)
        
        # Add source tag
        for v in verified:
            v["source"] = "Notion (WhatsApp Dump)"
            
        return verified
    except ImportError:
        print("   ❌ Could not import parse_whatsapp parser.")
        return []
    except Exception as e:
        print(f"   ❌ Error processing dump: {e}")
        return []

def main():
    ensure_tmp_dir()
    db_results = fetch_from_notion()
    dump_results = process_whatsapp_dump_page()
    
    all_results = db_results + dump_results
    
    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    
    # Create empty file if no results, to prevent pipeline cleaner errors
    if not all_results and not os.path.exists(CLEAN_OUTPUT):
         with open(CLEAN_OUTPUT, "w") as f:
            json.dump([], f)
            
    # Auto-Publish if we found items (especially from dump)
    if dump_results:
        import subprocess
        print(f"🚀 Publishing {len(dump_results)} items from Notion Dump...")
        subprocess.run(["python", "execution/publish_mnc_run.py", CLEAN_OUTPUT])

if __name__ == "__main__":
    main()
