"""
one_time_founders_run.py
--------------------------
One-time scrape for Founder's Office / AI Automation internships in India.
Preference: Onsite Chennai / Bangalore, but Remote India is included.

Steps:
  1. Scrape LinkedIn posts with focused queries
  2. Aggregate & score
  3. Create a NEW Google Sheet and publish to it
"""

import os
import sys
import json
import subprocess

# Ensure we can import from execution/
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

# ─── CONFIGURATION ─────────────────────────────────────────────────────────
TARGET = 60   # enough for a focused one-time run

NEW_SHEET_TITLE = "Founders Office & AI Automation Internships - India (March 2026)"

FOUNDER_QUERIES = [
    # Founder's Office
    '("founder\'s office" OR "founders office") AND (intern OR internship) AND (india OR bangalore OR chennai OR remote)',
    '(founder intern OR "chief of staff" intern OR "special projects" intern) AND (india OR bangalore OR chennai)',
    '(founder OR CEO OR "leadership team") AND (intern OR internship) AND (india OR chennai OR bangalore)',

    # AI / Automation
    '("AI automation" OR "AI agent" OR "workflow automation" OR n8n OR zapier) AND intern AND india',
    '("generative AI" OR llm OR "prompt engineering" OR AI) AND intern AND (india OR bangalore OR chennai OR remote)',
    '("automation intern" OR "AI intern" OR "tech intern") AND (india OR bangalore OR chennai OR remote)',

    # Broader catch
    '("startup intern" OR "early stage startup") AND (india OR bangalore OR chennai OR remote) AND (founder OR AI OR tech)',
    '(operations intern OR "growth intern" OR "strategy intern") AND (founder OR startup) AND (india OR bangalore OR chennai)',
]

# ─── STEP 1: Patch SEARCH QUERIES in scraper, run it ──────────────────────
def run_targeted_scrape():
    print("\n" + "="*60)
    print("STEP 1: Scraping LinkedIn for Founder's Office / AI Automation Internships")
    print("Targets: Chennai (first), Bangalore, Remote India")
    print("="*60)

    # We'll import and call into scrape_linkedin_posts directly
    # so we can override the queries and target count.
    try:
        import execution.scrape_linkedin_posts as scraper
    except ModuleNotFoundError:
        import scrape_linkedin_posts as scraper

    # Monkey-patch the search queries and target
    import types

    original_main = scraper.main

    def patched_main():
        from apify_client import ApifyClient
        import re

        scraper.ensure_tmp_dir()

        verified_posts = []
        seen_urls = set()

        # Use our focused queries
        search_queries = FOUNDER_QUERIES

        print("="*60)
        print("TARGETED SCRAPE - Founder's Office / AI Automation")
        print(f"Target: {TARGET} verified leads")
        print("="*60)

        # Configure LLM
        try:
            import llm_post_analyzer
        except ModuleNotFoundError:
            import execution.llm_post_analyzer as llm_post_analyzer
        llm_post_analyzer.configure_llm()
        print(f"✅ LLM: {llm_post_analyzer.PROVIDER.title()}")
        filter_posts_with_llm = llm_post_analyzer.filter_posts_with_llm
        use_llm = llm_post_analyzer.PROVIDER != "none"

        for i, query in enumerate(search_queries):
            if len(verified_posts) >= TARGET:
                print(f"\n🎉 Target {TARGET} reached!")
                break

            print(f"\n[{i+1}/{len(search_queries)}] Query: {query[:80]}...")
            print(f"   Progress: {len(verified_posts)}/{TARGET}")

            search_url = (
                "https://www.linkedin.com/search/results/content/"
                f"?datePosted=%22past-week%22"  # Use past-week for broader results
                f"&keywords={query.replace(' ', '%20')}&origin=FACETED_SEARCH"
            )
            run_input = {"urls": [search_url], "limitPerSource": 50}

            raw_posts = []
            try:
                raw_posts = scraper.run_apify_actor(scraper.PRIMARY_ACTOR, run_input)
            except Exception as e:
                print(f"   ❌ Primary failed: {e}. Trying fallback...")
                try:
                    raw_posts = scraper.run_apify_actor(scraper.FALLBACK_ACTOR, run_input)
                except Exception as e2:
                    print(f"   ❌ Fallback also failed: {e2}")
                    continue

            if not raw_posts:
                print("   ⚠️ No posts found")
                continue

            # Dedup
            new_unique = []
            for p in raw_posts:
                url = p.get("url") or p.get("post_url") or p.get("postUrl") or p.get("link")
                raw_text = p.get("text") or p.get("postText") or p.get("content") or ""
                norm_text = re.sub(r'[^\w\s]', '', raw_text[:300]).lower()
                norm_text = re.sub(r'\s+', ' ', norm_text).strip()[:150]
                text_hash = hash(norm_text) if norm_text else None

                # Block personal stories / job-seeking posts
                story_kw = ["i am looking for", "i'm looking for", "seeking a", "open to work", "my journey"]
                if any(kw in norm_text for kw in story_kw):
                    continue

                if text_hash and text_hash in seen_urls:
                    continue
                if url and url in seen_urls:
                    continue
                seen_urls.add(url or "")
                if text_hash:
                    seen_urls.add(text_hash)
                new_unique.append(p)

            print(f"   {len(new_unique)} unique new posts after dedup")
            if not new_unique:
                continue

            # LLM Extraction
            batch_verified = []
            if use_llm:
                print("   🤖 LLM extraction...")
                llm_results = filter_posts_with_llm(new_unique)
                for post in llm_results:
                    analysis = post.get("llm_analysis", {})
                    if isinstance(analysis, list):
                        analysis = analysis[0] if analysis else {}

                    llm_company = analysis.get("company") or ""
                    llm_roles = analysis.get("roles", [])
                    llm_location = analysis.get("location") or ""
                    llm_work_type = analysis.get("work_type") or ""

                    author_name = post.get("authorName") or post.get("author", {}).get("name", "") or ""
                    author_headline = post.get("authorHeadline") or post.get("author", {}).get("headline", "") or ""
                    post_text = post.get("text") or post.get("postText") or post.get("content") or ""
                    url = post.get("url") or post.get("postUrl") or post.get("link") or ""

                    # Location filter — prioritise Chennai, Bangalore, remote India
                    india_kw = [
                        "india", "remote", "work from home", "wfh", "pan india",
                        "bangalore", "bengaluru", "chennai", "mumbai", "delhi",
                        "hyderabad", "pune", "noida", "gurgaon", "gurugram",
                    ]
                    loc_lower = llm_location.lower()
                    text_lower = post_text.lower()
                    if not any(k in loc_lower or k in text_lower for k in india_kw):
                        print(f"    ❌ Not India: {llm_location or 'Unknown'}")
                        continue

                    final_company = llm_company if llm_company not in [None, "", "null", "Unknown"] else author_name
                    final_role = llm_roles[0] if llm_roles else "Internship"
                    final_location = llm_location if llm_location not in [None, "", "null"] else ""

                    clean_post = {
                        "author_name": author_name,
                        "author_headline": author_headline,
                        "post_text": post_text[:500],
                        "posted_time": post.get("postedTime") or post.get("postedAtISO") or "",
                        "likes": post.get("likes") or 0,
                        "comments": post.get("comments") or 0,
                        "url": url,
                        "title": final_role,
                        "type": analysis.get("type") or "",
                        "timing": analysis.get("timing") or "",
                        "description": post_text[:5000],
                        "stipend": analysis.get("stipend") or "",
                        "duration": analysis.get("duration") or "",
                        "experience": analysis.get("experience") or "",
                        "location": final_location,
                        "deadline": analysis.get("deadline") or "",
                        "tags": analysis.get("tags") or [],
                        "hiringOrganization": final_company,
                        "contact_email": analysis.get("contact_email") or "",
                        "apply_link": analysis.get("apply_link") or "",
                        "role": final_role,
                        "company": final_company,
                        "work_type": llm_work_type,
                        "hiring_signals": ["llm_extracted"],
                        "engagement_score": 1,
                        "freshness_bonus": 1,
                        "is_stale": False,
                    }
                    batch_verified.append(clean_post)
            else:
                batch_verified = scraper.filter_posts(new_unique)

            print(f"   ✅ {len(batch_verified)} leads from this batch")
            verified_posts.extend(batch_verified)

        # Save clean output (same file read by aggregate_and_score.py)
        with open(scraper.CLEAN_OUTPUT, "w", encoding="utf-8") as f:
            json.dump(verified_posts, f, indent=2, ensure_ascii=False)
        print(f"\nSaved {len(verified_posts)} posts → {scraper.CLEAN_OUTPUT}")
        return verified_posts

    return patched_main()


# ─── STEP 2: Aggregate & Score ─────────────────────────────────────────────
def run_aggregate():
    print("\n" + "="*60)
    print("STEP 2: Aggregating & Scoring")
    print("="*60)
    result = subprocess.run(
        [sys.executable, "execution/aggregate_and_score.py"],
        env={**os.environ, "PYTHONUNBUFFERED": "1"}
    )
    return result.returncode == 0


# ─── STEP 3: Create NEW sheet and publish ──────────────────────────────────
def create_new_sheet_and_publish():
    print("\n" + "="*60)
    print("STEP 3: Creating New Google Sheet & Publishing")
    print(f"Sheet Name: {NEW_SHEET_TITLE}")
    print("="*60)

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    CREDENTIALS_FILE = "credentials.json"
    TOKEN_FILE = "token.json"

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    sheets_svc = build("sheets", "v4", credentials=creds)
    drive_svc = build("drive", "v3", credentials=creds)

    # Create new spreadsheet
    sheet_body = {"properties": {"title": NEW_SHEET_TITLE}}
    spreadsheet = sheets_svc.spreadsheets().create(body=sheet_body, fields="spreadsheetId").execute()
    sheet_id = spreadsheet["spreadsheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    print(f"✅ Created new sheet: {sheet_url}")

    # Make it accessible (anyone with link can view)
    drive_svc.permissions().create(
        fileId=sheet_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # Load data
    input_file = os.path.join(".tmp", "final_ranked_internships.json")
    with open(input_file, encoding="utf-8") as f:
        internships = json.load(f)

    print(f"Loaded {len(internships)} internships to publish...")

    # Headers
    HEADERS = [
        "Title", "Company", "Location", "Work Type", "Stipend", "Duration",
        "Experience", "Timing", "Deadline", "Tags", "Description",
        "Post URL", "Apply Link", "Contact Email", "Date Added"
    ]

    rows = [HEADERS]
    for item in internships:
        tags = item.get("tags", [])
        if isinstance(tags, list):
            tags = ", ".join(tags)
        rows.append([
            item.get("title") or item.get("role") or "",
            item.get("company") or item.get("hiringOrganization") or "",
            item.get("location") or "",
            item.get("work_type") or item.get("type") or "",
            item.get("stipend") or "",
            item.get("duration") or "",
            item.get("experience") or "",
            item.get("timing") or "",
            item.get("deadline") or "",
            tags,
            (item.get("description") or item.get("post_text") or "")[:300],
            item.get("url") or "",
            item.get("apply_link") or "",
            item.get("contact_email") or "",
            item.get("posted_time") or "",
        ])

    sheets_svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Bold the header row
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "requests": [
                {
                    "repeatCell": {
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold",
                    }
                },
                {
                    "autoResizeDimensions": {
                        "dimensions": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": len(HEADERS)}
                    }
                },
            ]
        },
    ).execute()

    print(f"\n{'='*60}")
    print(f"✅ Published {len(internships)} internships!")
    print(f"📊 Sheet URL: {sheet_url}")
    print(f"{'='*60}")
    return sheet_url


# ─── MAIN ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    posts = run_targeted_scrape()
    print(f"\nScrape done: {len(posts)} posts")

    if posts:
        ok = run_aggregate()
        if not ok:
            print("⚠️ Aggregate step failed. Trying to publish whatever was scraped...")

        url = create_new_sheet_and_publish()
        print(f"\n✅ All done! Open: {url}")
    else:
        print("\n❌ No posts scraped. Check your API keys and queries.")
