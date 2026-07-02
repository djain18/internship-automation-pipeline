"""
bangalore_remote_run.py
-----------------------
Custom run: India-based companies, REMOTE / WFH only (no on-site required).
Roles: Digital Marketing, Business Development, Product Manager,
       Founder's Office, Finance, Research Analyst, Operations,
       AI Automation, Generalist, Growth, and related growth/company-building roles.
Stipend: Extracted and shown clearly; "Not Specified" when missing.
"""

import os
import sys
import json
import re
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from apify_client import ApifyClient
import execution.llm_post_analyzer as llm
import execution.publish_to_sheets as pub_utils
import execution.format_google_sheet as formatter

llm.configure_llm()
print(f"Using Provider: {llm.PROVIDER}")

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_COUNT   = 60
ACTOR_ID       = "supreme_coder/linkedin-post"
TMP_DIR        = ".tmp"
os.makedirs(TMP_DIR, exist_ok=True)
CLEAN_FILE     = os.path.join(TMP_DIR, "india_remote_clean.json")

# ── Search Queries ────────────────────────────────────────────────────────────
# India-wide remote internships across all target role clusters
SEARCH_QUERIES = [
    # Founder's Office / Chief of Staff / Generalist
    '("founder\'s office" OR "chief of staff" OR generalist) AND (intern OR internship) AND (india OR remote) AND (remote OR "work from home" OR wfh)',
    'hiring "founder\'s office intern" remote india',
    'hiring "generalist intern" remote india',

    # AI / Automation
    '("ai automation" OR "ai engineer" OR "machine learning") AND (intern OR internship) AND india AND (remote OR "work from home")',
    'hiring "ai automation intern" remote india',

    # Digital Marketing / Growth
    '("digital marketing" OR "growth marketing" OR "performance marketing" OR "social media marketing") AND (intern OR internship) AND india AND (remote OR "work from home" OR wfh)',
    'hiring "digital marketing intern" remote india',
    'hiring "growth intern" remote india',

    # Business Development
    '("business development" OR "bd intern") AND (intern OR internship) AND india AND (remote OR "work from home" OR wfh)',
    'hiring "business development intern" remote india',

    # Product Management
    '("product manager" OR "product management" OR "pm intern") AND (intern OR internship) AND india AND (remote OR "work from home")',
    'hiring "product management intern" remote india',

    # Finance / Accounts
    '("finance intern" OR "financial analyst intern") AND india AND (remote OR "work from home" OR wfh)',
    'hiring "finance intern" remote india',

    # Research Analyst
    '("research analyst" OR "market research" OR "research intern") AND india AND (remote OR "work from home" OR wfh)',
    'hiring "research intern" remote india',

    # Operations
    '("operations intern" OR "ops intern" OR "strategy and operations") AND india AND (remote OR "work from home" OR wfh)',
    'hiring "operations intern" remote india',

    # Strategy / GTM / Growth (company-building catchall)
    '("strategy intern" OR "growth intern" OR "gtm" OR "go-to-market") AND india AND (remote OR "work from home" OR wfh)',
    'hiring "strategy intern" remote india',
]

# Role keywords used for relevance scoring / boost
PRIORITY_ROLES = [
    "founder", "office", "chief of staff", "generalist", "ai automation", "ai engineer",
    "digital marketing", "growth", "business development", "product manager", "product management",
    "finance", "financial analyst", "research analyst", "operations", "ops", "strategy",
    "consulting", "gtm", "go-to-market", "performance marketing", "social media"
]


def run_apify_search(query: str, limit: int = 60) -> list:
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set")
        return []

    client = ApifyClient(api_token)
    encoded_query = query.replace(' ', '%20')
    search_url = (
        f"https://www.linkedin.com/search/results/content/"
        f"?datePosted=%22past-week%22&keywords={encoded_query}&origin=FACETED_SEARCH"
    )

    print(f"\nScraping: {query[:80]}...")
    try:
        run = client.actor(ACTOR_ID).call(run_input={"urls": [search_url], "limitPerSource": limit})
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"  > {len(items)} raw posts retrieved")
        return items
    except Exception as e:
        print(f"  > Apify error: {e}")
        return []


def is_remote_india(location: str, post_text: str) -> bool:
    """
    Accept only if:
      - Remote / WFH signal is present (no on-site commute required), AND
      - India context is present (any Indian city, state, or 'India').
    Reject if explicitly on-site only, hybrid-only, or foreign-only remote.
    """
    loc  = (location or "").lower()
    text = (post_text or "").lower()
    combined = loc + " " + text

    # Hard reject: explicitly requires physical presence
    if re.search(r'\b(no remote|not remote|on.?site only|in.?office only|must relocate|office mandatory)\b', combined):
        return False

    # Hard reject: hybrid-only (must come in part-time)
    if re.search(r'\bhybrid only\b', combined):
        return False

    # Hard reject: foreign-only
    foreign = [
        "usa", "us only", "uk only", "united states", "united kingdom", "canada",
        "australia", "germany", "france", "europe", "dubai", "uae", "singapore",
        "malaysia", "london", "new york", "san francisco", "california",
        "remote us", "remote uk", "remote canada", "remote australia"
    ]
    for fw in foreign:
        if re.search(r'\b' + re.escape(fw) + r'\b', combined):
            return False

    has_remote = bool(re.search(
        r'\b(remote|work from home|wfh|work.?from.?anywhere|fully remote|100.?remote|virtual)\b',
        combined
    ))

    # Accept any Indian city/state signal — very broad intentionally
    has_india = bool(re.search(
        r'\b(india|indian|bangalore|bengaluru|mumbai|delhi|hyderabad|pune|chennai|'
        r'kolkata|ahmedabad|jaipur|noida|gurgaon|gurugram|chandigarh|lucknow|'
        r'indore|bhopal|surat|vadodara|kochi|thiruvananthapuram|coimbatore|'
        r'nagpur|visakhapatnam|pan.?india)\b',
        combined
    ))

    return has_remote and has_india


def is_relevant_role(role: str, post_text: str) -> bool:
    """Broad filter — keep anything that sounds like a company-building role."""
    combined = (role + " " + post_text).lower()
    return any(kw in combined for kw in PRIORITY_ROLES) or \
           re.search(r'\b(intern|internship)\b', combined) is not None


def scrape_and_process():
    verified_posts = []
    seen_urls  = set()
    seen_roles = set()

    for query in SEARCH_QUERIES:
        if len(verified_posts) >= TARGET_COUNT:
            break

        raw_items = run_apify_search(query, 80)

        unique_items = []
        for p in raw_items:
            url = p.get("url") or p.get("postUrl") or p.get("link")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_items.append(p)

        if not unique_items:
            continue

        print(f"   Analyzing {len(unique_items)} unique posts with LLM...")
        llm_results = llm.filter_posts_with_llm(unique_items)

        for post in llm_results:
            analysis = post.get("llm_analysis", {})
            if isinstance(analysis, list):
                analysis = analysis[0] if analysis else {}

            company   = analysis.get("company", "")
            roles     = analysis.get("roles", [])
            role      = roles[0] if roles else "Internship"
            location  = analysis.get("location", "Unknown")
            post_text = post.get("text", "")[:5000]

            if not is_remote_india(location, post_text):
                continue

            # Deduplicate by role+company pair
            role_key = f"{role.lower().strip()}_{company.lower().strip()}"
            if role_key in seen_roles:
                print(f"     ♻️  Skipping duplicate: {role} @ {company}")
                continue
            seen_roles.add(role_key)

            # Stipend: be explicit when missing
            raw_stipend = analysis.get("stipend", "")
            stipend_display = raw_stipend if raw_stipend and raw_stipend.strip() else "Not Specified"

            boost_score = 5 if any(kw in (role + company).lower() for kw in PRIORITY_ROLES) else 1

            clean_record = {
                "title":             role,
                "role":              role,
                "type":              analysis.get("type", "Internship"),
                "timing":            analysis.get("timing", ""),
                "description":       post_text,
                "stipend":           stipend_display,
                "stipend_available": stipend_display != "Not Specified",
                "duration":          analysis.get("duration", ""),
                "experience":        analysis.get("experience", ""),
                "location":          location,
                "deadline":          analysis.get("deadline", ""),
                "tags":              analysis.get("tags", []),
                "hiringOrganization":company,
                "company":           company,
                "author_name":       post.get("authorName", "") or post.get("author", {}).get("name", "N/A"),
                "url":               post.get("url", "") or post.get("postUrl", ""),
                "apply_link":        analysis.get("apply_link", ""),
                "contact_email":     analysis.get("contact_email", ""),
                "engagement_score":  boost_score,
                "is_stale":          False,
                "freshness_bonus":   1,
            }
            verified_posts.append(clean_record)
            stipend_note = f"Stipend: {stipend_display}" if stipend_display != "Not Specified" else "⚠️  No stipend info"
            print(f"     ✅  {role} @ {company} | {location} | {stipend_note}")

            if len(verified_posts) >= TARGET_COUNT:
                break

    with open(CLEAN_FILE, "w", encoding="utf-8") as f:
        json.dump(verified_posts, f, indent=2)

    print(f"\nFinal verified count: {len(verified_posts)}")
    return verified_posts


def create_fresh_sheet_and_publish(items):
    if not items:
        print("Nothing to publish.")
        return

    print("\nConnecting to Google Sheets...")
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pub_utils.CREDENTIALS_FILE = os.path.join(root_dir, "credentials.json")
    pub_utils.TOKEN_FILE       = os.path.join(root_dir, "token.json")

    service = pub_utils.get_sheets_service()

    title = f"India Remote Internships – {datetime.now().strftime('%b %d, %Y')}"
    spreadsheet = service.spreadsheets().create(
        body={"properties": {"title": title}},
        fields="spreadsheetId"
    ).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    print(f"Created sheet: {sheet_id}")

    HEADERS = [
        "Role", "Type", "Timing", "Description", "Stipend", "Stipend Available",
        "Duration", "Experience", "Location", "Deadline", "Tags",
        "Company", "Hiring Manager", "Post URL", "Apply Link", "Contact Email", "Date Added"
    ]

    rows = []
    for item in items:
        tags = item.get("tags", [])
        tags_str = ", ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)

        rows.append([
            item.get("role", ""),
            item.get("type", "Internship"),
            item.get("timing", ""),
            item.get("description", ""),
            item.get("stipend", "Not Specified"),
            "Yes" if item.get("stipend_available") else "No",
            item.get("duration", ""),
            item.get("experience", ""),
            item.get("location", ""),
            item.get("deadline", ""),
            tags_str,
            item.get("company", ""),
            item.get("author_name", ""),
            item.get("url", ""),
            item.get("apply_link", ""),
            item.get("contact_email", ""),
            datetime.now().strftime("%Y-%m-%d"),
        ])

    # Write headers
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Sheet1!A1:Q1",
        valueInputOption="RAW",
        body={"values": [HEADERS]}
    ).execute()

    # Append data
    if rows:
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Sheet1!A2",
            valueInputOption="RAW",
            body={"values": rows}
        ).execute()
        print(f"Published {len(rows)} internships.")

    try:
        formatter.apply_formatting(sheet_id)
    except Exception as e:
        print(f"Formatting warning: {e}")

    print("\n" + "=" * 55)
    print("✅  RUN COMPLETE")
    print(f"Sheet : {title}")
    print(f"URL   : https://docs.google.com/spreadsheets/d/{sheet_id}")
    print("=" * 55)
    return sheet_id


if __name__ == "__main__":
    print("=" * 55)
    print("India Remote Internship Run (WFH only)")
    print(f"Roles: Digital Marketing, BizDev, Product, Founder's")
    print(f"       Office, Finance, Research, Ops, AI, Generalist,")
    print(f"       Growth + related company-building roles")
    print(f"Location filter: India (any city) + Remote/WFH ONLY")
    print("=" * 55)

    items = scrape_and_process()
    if items:
        create_fresh_sheet_and_publish(items)
    else:
        print("No matching internships found. Try again later.")
