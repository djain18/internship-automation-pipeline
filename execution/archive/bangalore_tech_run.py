"""
bangalore_tech_run.py
----------------------
Custom run: Tech internships in Bangalore (on-site) OR Remote/WFH (India-based).
Roles: Frontend Developer, Backend Developer, Full Stack Developer,
       AI Automation, Founder's Office, and all related tech/engineering roles.
Target: 100+ internships published to a fresh Google Sheet.
"""

import os
import sys
import json
import re
import logging
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

# Silence Apify's noisy streamed actor logs. The supreme_coder/linkedin-post actor
# emits internal retry warnings ("no available accounts found",
# "searchDashClustersByAll", "No more posts found") that it recovers from
# automatically — they are NOT fatal. Suppressing them keeps our own progress
# output readable. We rely on the run status + dataset length to judge success.
for _noisy in ("apify", "apify_client"):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL)
    logging.getLogger(_noisy).propagate = False

from apify_client import ApifyClient
import execution.llm_post_analyzer as llm
import execution.publish_to_sheets as pub_utils
import execution.format_google_sheet as formatter

llm.configure_llm()
print(f"Using Provider: {llm.PROVIDER}")

# ── Config ─────────────────────────────────────────────────────────────────────
TARGET_COUNT = 120   # aim for 120 to guarantee 100+ after any late drops
ACTOR_ID     = "supreme_coder/linkedin-post"
TMP_DIR      = ".tmp"
os.makedirs(TMP_DIR, exist_ok=True)
CLEAN_FILE   = os.path.join(TMP_DIR, "bangalore_tech_clean.json")

# ── Search Queries ─────────────────────────────────────────────────────────────
SEARCH_QUERIES = [
    # ── Frontend ──────────────────────────────────────────────────────────────
    '("frontend developer" OR "front end developer" OR "frontend engineer" OR "react developer") AND (intern OR internship) AND (bangalore OR bengaluru)',
    '("frontend developer" OR "front end developer" OR "react developer" OR "vue developer" OR "angular developer") AND (intern OR internship) AND (india OR remote) AND (remote OR "work from home" OR wfh)',
    'hiring "frontend intern" bangalore',
    'hiring "frontend intern" remote india',
    'hiring "react intern" india',

    # ── Backend ───────────────────────────────────────────────────────────────
    '("backend developer" OR "back end developer" OR "backend engineer" OR "node.js developer" OR "python developer") AND (intern OR internship) AND (bangalore OR bengaluru)',
    '("backend developer" OR "back end developer" OR "django" OR "fastapi" OR "node.js" OR "express") AND (intern OR internship) AND (india OR remote) AND (remote OR "work from home" OR wfh)',
    'hiring "backend intern" bangalore',
    'hiring "backend intern" remote india',
    'hiring "python intern" backend india',

    # ── Full Stack ────────────────────────────────────────────────────────────
    '("full stack developer" OR "fullstack developer" OR "full-stack engineer" OR "mern" OR "mean stack") AND (intern OR internship) AND (bangalore OR bengaluru)',
    '("full stack developer" OR "fullstack developer" OR "mern stack" OR "mean stack") AND (intern OR internship) AND (india OR remote) AND (remote OR "work from home" OR wfh)',
    'hiring "full stack intern" bangalore',
    'hiring "full stack intern" remote india',
    'hiring "mern intern" india',

    # ── AI / ML / Automation / GenAI ─────────────────────────────────────────
    '("ai automation" OR "machine learning" OR "ai engineer" OR "llm" OR "generative ai" OR "data science") AND (intern OR internship) AND (bangalore OR bengaluru)',
    '("ai automation" OR "machine learning" OR "llm engineer" OR "generative ai" OR "nlp") AND (intern OR internship) AND (india OR remote) AND (remote OR "work from home" OR wfh)',
    '("prompt engineer" OR "ai researcher" OR "ai product" OR "computer vision" OR "deep learning") AND (intern OR internship) AND (india OR bangalore OR remote)',
    '("rag" OR "langchain" OR "fine tuning" OR "ai agent" OR "agentic ai") AND (intern OR internship) AND (india OR bangalore OR remote)',
    'hiring "ai intern" bangalore',
    'hiring "ai automation intern" remote india',
    'hiring "machine learning intern" india',
    'hiring "data science intern" bangalore',
    'hiring "generative ai intern" india remote',
    'hiring "llm intern" india remote',

    # ── AI UGC / AI Content / AI Video ───────────────────────────────────────
    '("ai ugc" OR "ugc content" OR "ai video" OR "ai content creator") AND (intern OR internship) AND (india OR bangalore OR remote)',
    '("content creation" OR "ugc creator" OR "video content" OR "short form content") AND (ai OR automation) AND (intern OR internship) AND (india OR bangalore OR remote)',
    'hiring "ai content intern" india remote',
    'hiring "ugc intern" india remote',
    '("social media" OR "content marketing" OR "reels" OR "short form video") AND (ai OR automation) AND (intern OR internship) AND (india OR bangalore)',

    # ── Founder's Office / Chief of Staff / Growth ────────────────────────────
    '("founder\'s office" OR "chief of staff" OR "founder office") AND (intern OR internship) AND (bangalore OR bengaluru)',
    '("founder\'s office" OR "chief of staff" OR generalist) AND (intern OR internship) AND (india OR remote) AND (remote OR "work from home" OR wfh)',
    '("growth intern" OR "growth hacker" OR "growth marketing") AND (intern OR internship) AND (india OR bangalore OR remote)',
    '("business development" OR "bd intern" OR "sales intern") AND (intern OR internship) AND (india OR bangalore OR remote) AND (remote OR "work from home" OR wfh OR bangalore)',
    '("product management" OR "pm intern" OR "product intern") AND (intern OR internship) AND (india OR bangalore OR remote)',
    '("operations intern" OR "strategy intern" OR "gtm intern") AND (india OR bangalore OR remote)',
    'hiring "founder\'s office intern" bangalore',
    'hiring "founder\'s office intern" remote india',
    'hiring "chief of staff intern" india',
    'hiring "growth intern" india remote',
    'hiring "product intern" bangalore india',

    # ── SDE / Software Engineering ───────────────────────────────────────────
    '("software developer" OR "software engineer" OR "sde" OR "swe") AND (intern OR internship) AND (bangalore OR bengaluru)',
    '("software developer intern" OR "software engineering intern" OR "sde intern") AND (india OR remote) AND (remote OR "work from home" OR wfh)',
    'hiring "software engineering intern" bangalore',
    'hiring "sde intern" remote india',

    # ── DevOps / Cloud ───────────────────────────────────────────────────────
    '("devops" OR "cloud engineer" OR "aws" OR "gcp" OR "kubernetes" OR "docker") AND (intern OR internship) AND (bangalore OR bengaluru)',
    'hiring "devops intern" india remote',

    # ── Mobile ───────────────────────────────────────────────────────────────
    '("android developer" OR "ios developer" OR "flutter developer" OR "react native") AND (intern OR internship) AND (bangalore OR bengaluru)',
    'hiring "mobile developer intern" bangalore india',

    # ── Broader catchall queries for volume ───────────────────────────────────
    'hiring "tech intern" bangalore 2024 2025',
    'hiring "developer intern" bangalore remote india',
    'hiring "engineering intern" bangalore india',
    '"open for internship" (frontend OR backend OR fullstack OR "full stack" OR ai OR ml) bangalore',
    '"open for internship" (frontend OR backend OR fullstack OR "full stack" OR ai OR ml) remote india',
]

# Role keywords for relevance scoring and tab assignment
PRIORITY_ROLES = [
    "frontend", "front end", "react", "vue", "angular", "javascript", "typescript",
    "backend", "back end", "node", "python", "django", "fastapi", "express", "java", "spring",
    "full stack", "fullstack", "mern", "mean", "next.js", "nuxt",
    "ai", "automation", "machine learning", "llm", "generative ai", "nlp", "data science",
    "prompt engineer", "ai researcher", "computer vision", "deep learning", "rag", "langchain",
    "ai agent", "fine tuning", "ai product",
    "ugc", "ai ugc", "ai video", "ai content", "content creator", "short form", "video content",
    "founder", "chief of staff", "generalist",
    "growth", "growth marketing", "growth hacker", "business development", "bd intern",
    "product manager", "product management", "pm intern", "product intern",
    "operations", "ops intern", "strategy", "gtm", "go-to-market", "sales intern",
    "software developer", "software engineer", "sde", "swe",
    "devops", "cloud", "kubernetes", "docker",
    "android", "ios", "flutter", "react native", "mobile",
]

# Tab assignment: maps each record to a sheet tab by role keywords
TAB_RULES = [
    ("Frontend",          ["frontend", "front end", "react", "vue", "angular", "javascript", "typescript", "next.js", "nuxt", "svelte", "css", "html"]),
    ("Backend",           ["backend", "back end", "node.js", "python", "django", "fastapi", "express", "java", "spring", "golang", "ruby", "php", "api developer"]),
    ("Full Stack",        ["full stack", "fullstack", "mern", "mean stack", "full-stack"]),
    ("AI & ML",           ["machine learning", "deep learning", "nlp", "computer vision", "data science", "ai researcher", "prompt engineer", "rag", "langchain", "fine tuning", "ai agent", "generative ai", "llm", "ai engineer", "ai product"]),
    ("AI Automation",     ["ai automation", "automation engineer", "rpa", "workflow automation", "zapier", "make.com", "n8n"]),
    ("AI UGC & Content",  ["ugc", "ai ugc", "ai video", "ai content", "content creator", "short form", "video content", "reels", "social media"]),
    ("Founder's Office",  ["founder", "chief of staff", "founder's office", "founder office"]),
    ("Growth & BizDev",   ["growth", "growth marketing", "growth hacker", "business development", "bd intern", "sales intern", "gtm", "go-to-market"]),
    ("Product & Ops",     ["product manager", "product management", "pm intern", "product intern", "operations", "ops intern", "strategy intern"]),
    ("SDE & DevOps",      ["software developer", "software engineer", "sde", "swe", "devops", "cloud engineer", "kubernetes", "docker", "aws", "gcp", "site reliability"]),
    ("Mobile",            ["android", "ios developer", "flutter", "react native", "mobile developer"]),
]


def _query_to_url(query: str) -> str:
    # past-month (not past-week) for a much larger candidate pool — needed to
    # clear the 100+ target after location/dedup/quality filtering.
    encoded = query.replace(' ', '%20')
    return (
        f"https://www.linkedin.com/search/results/content/"
        f"?datePosted=%22past-month%22&keywords={encoded}&origin=FACETED_SEARCH"
    )


def run_apify_batch(queries: list, limit: int = 60) -> list:
    """
    Scrape MANY search queries in a single actor run by passing all their URLs
    in one call. This is far faster than one actor run per query — it collapses
    dozens of container cold-starts (~30-60s each) into a single run.

    logger=None silences the actor's verbose internal retry log (those
    "no available accounts found" / "searchDashClustersByAll" warnings are
    non-fatal; the actor recovers on its own).
    """
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set")
        return []

    client = ApifyClient(api_token)
    urls = [_query_to_url(q) for q in queries]

    print(f"\nBatch scraping {len(urls)} queries (limit {limit}/query)...")
    for attempt in range(2):
        try:
            run = client.actor(ACTOR_ID).call(
                run_input={"urls": urls, "limitPerSource": limit},
                logger=None,
            )
            status = run.get("status")
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            print(f"  > {status}: {len(items)} raw posts retrieved from batch")
            return items
        except Exception as e:
            msg = str(e).splitlines()[0] if str(e) else repr(e)
            if attempt == 0:
                print(f"  > transient error, retrying once: {msg[:120]}")
                continue
            print(f"  > Apify error: {msg[:160]}")
            return []


def run_apify_search(query: str, limit: int = 80) -> list:
    """Single-query convenience wrapper (kept for smoke tests / reuse)."""
    return run_apify_batch([query], limit=limit)


def is_bangalore_or_remote_india(location: str, post_text: str) -> bool:
    """
    Accept if:
      (a) Bangalore / Bengaluru on-site, OR
      (b) Remote/WFH with India context.
    Reject explicit on-site-only (non-Bangalore) or foreign-only remote.
    """
    loc  = (location or "").lower()
    text = (post_text or "").lower()
    combined = loc + " " + text

    # Hard reject: explicitly no remote and not Bangalore
    if re.search(r'\b(no remote|not remote|on.?site only|in.?office only|must relocate|office mandatory)\b', combined):
        blr = bool(re.search(r'\b(bangalore|bengaluru)\b', combined))
        if not blr:
            return False

    # Hard reject: foreign-only
    foreign = [
        "usa", "us only", "uk only", "united states", "united kingdom",
        "canada", "australia", "germany", "france", "europe",
        "dubai", "uae", "singapore", "malaysia",
        "london", "new york", "san francisco", "california",
        "remote us", "remote uk", "remote canada", "remote australia",
    ]
    for fw in foreign:
        if re.search(r'\b' + re.escape(fw) + r'\b', combined):
            return False

    # Accept: Bangalore on-site
    is_bangalore = bool(re.search(r'\b(bangalore|bengaluru)\b', combined))
    if is_bangalore:
        return True

    # Accept: Remote + India
    has_remote = bool(re.search(
        r'\b(remote|work from home|wfh|work.?from.?anywhere|fully remote|100.?remote|virtual)\b',
        combined
    ))
    has_india = bool(re.search(
        r'\b(india|indian|mumbai|delhi|hyderabad|pune|chennai|kolkata|ahmedabad|'
        r'jaipur|noida|gurgaon|gurugram|chandigarh|lucknow|indore|bhopal|surat|'
        r'vadodara|kochi|thiruvananthapuram|coimbatore|nagpur|visakhapatnam|pan.?india)\b',
        combined
    ))

    return has_remote and has_india


BATCH_SIZE = 10   # search URLs per actor run — collapses cold-starts


def scrape_and_process():
    verified_posts = []
    seen_urls  = set()
    seen_roles = set()

    # ── Phase 1: scrape ALL queries in batched actor runs ──────────────────────
    raw_pool = []
    for i in range(0, len(SEARCH_QUERIES), BATCH_SIZE):
        batch = SEARCH_QUERIES[i:i + BATCH_SIZE]
        print(f"\n=== Batch {i // BATCH_SIZE + 1} of "
              f"{(len(SEARCH_QUERIES) + BATCH_SIZE - 1) // BATCH_SIZE} ===")
        raw_pool.extend(run_apify_batch(batch, limit=70))

    # ── Phase 2: dedup by post URL across the entire pool ──────────────────────
    unique_items = []
    for p in raw_pool:
        url = p.get("url") or p.get("postUrl") or p.get("link")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_items.append(p)

    print(f"\nScraped {len(raw_pool)} raw posts -> {len(unique_items)} unique.")
    if not unique_items:
        print("No posts scraped.")
        return []

    # ── Phase 3: a single LLM pass over the whole unique pool ───────────────────
    print(f"Analyzing {len(unique_items)} unique posts with LLM (one pass)...")
    llm_results = llm.filter_posts_with_llm(unique_items)

    # ── Phase 4: location + role filtering and record assembly ─────────────────
    for post in llm_results:
        if len(verified_posts) >= TARGET_COUNT:
            break

        analysis = post.get("llm_analysis", {})
        if isinstance(analysis, list):
            analysis = analysis[0] if analysis else {}

        company   = analysis.get("company", "")
        roles     = analysis.get("roles", [])
        role      = roles[0] if roles else "Internship"
        location  = analysis.get("location", "Unknown")
        post_text = post.get("text", "")[:5000]

        if not is_bangalore_or_remote_india(location, post_text):
            continue

        role_key = f"{role.lower().strip()}_{company.lower().strip()}"
        if role_key in seen_roles:
            continue
        seen_roles.add(role_key)

        raw_stipend = analysis.get("stipend", "")
        stipend_display = raw_stipend if raw_stipend and raw_stipend.strip() else "Not Specified"

        # Determine work mode label
        combined_loc = (location + " " + post_text).lower()
        if re.search(r'\b(bangalore|bengaluru)\b', combined_loc):
            if re.search(r'\b(remote|wfh|work from home)\b', combined_loc):
                work_mode = "Bangalore / Remote"
            else:
                work_mode = "Bangalore (On-site)"
        else:
            work_mode = "Remote (India)"

        boost_score = 5 if any(kw in (role + company).lower() for kw in PRIORITY_ROLES) else 1

        clean_record = {
            "title":             role,
            "role":              role,
            "type":              analysis.get("type", "Internship"),
            "timing":            analysis.get("timing", ""),
            "work_mode":         work_mode,
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
        stipend_note = f"Stipend: {stipend_display}" if stipend_display != "Not Specified" else "No stipend info"
        print(f"  ✅  {role} @ {company} | {work_mode} | {stipend_note}")

    with open(CLEAN_FILE, "w", encoding="utf-8") as f:
        json.dump(verified_posts, f, indent=2)

    print(f"\nFinal verified count: {len(verified_posts)}")
    return verified_posts


def assign_tab(role: str, description: str) -> str:
    """Return the tab name that best matches this internship."""
    combined = (role + " " + description).lower()
    for tab_name, keywords in TAB_RULES:
        if any(kw in combined for kw in keywords):
            return tab_name
    return "Other"


def _make_row(item: dict) -> list:
    tags = item.get("tags", [])
    tags_str = ", ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)
    return [
        item.get("role", ""),
        item.get("type", "Internship"),
        item.get("work_mode", ""),
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
    ]


def create_fresh_sheet_and_publish(items):
    if not items:
        print("Nothing to publish.")
        return

    print("\nConnecting to Google Sheets...")
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pub_utils.CREDENTIALS_FILE = os.path.join(root_dir, "credentials.json")
    pub_utils.TOKEN_FILE       = os.path.join(root_dir, "token.json")

    service = pub_utils.get_sheets_service()

    HEADERS = [
        "Role", "Type", "Work Mode", "Timing", "Description", "Stipend", "Stipend Available",
        "Duration", "Experience", "Location", "Deadline", "Tags",
        "Company", "Hiring Manager", "Post URL", "Apply Link", "Contact Email", "Date Added"
    ]

    # Bucket items by tab
    buckets: dict[str, list] = {}
    for item in items:
        tab = assign_tab(item.get("role", ""), item.get("description", ""))
        item["_tab"] = tab
        buckets.setdefault(tab, []).append(item)

    # Build tab names: "All" first, then populated role tabs in TAB_RULES order, then "Other"
    populated_tabs = [name for name, _ in TAB_RULES if name in buckets]
    if "Other" in buckets:
        populated_tabs.append("Other")
    all_tabs = ["All"] + populated_tabs

    # Create spreadsheet with all required sheets in one call
    sheet_requests = [{"addSheet": {"properties": {"title": t}}} for t in all_tabs if t != "Sheet1"]
    title = f"Bangalore + Remote Tech Internships – {datetime.now().strftime('%b %d, %Y')}"

    spreadsheet = service.spreadsheets().create(
        body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": t}} for t in all_tabs],
        },
        fields="spreadsheetId,sheets.properties"
    ).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    print(f"Created sheet: {sheet_id}")

    # Write each tab
    def write_tab(tab_name: str, rows: list):
        range_hdr = f"'{tab_name}'!A1:R1"
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=range_hdr,
            valueInputOption="RAW",
            body={"values": [HEADERS]}
        ).execute()
        if rows:
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"'{tab_name}'!A2",
                valueInputOption="RAW",
                body={"values": rows}
            ).execute()
        print(f"  Tab '{tab_name}': {len(rows)} rows")

    all_rows = [_make_row(i) for i in items]
    write_tab("All", all_rows)

    for tab_name in populated_tabs:
        tab_rows = [_make_row(i) for i in buckets.get(tab_name, [])]
        write_tab(tab_name, tab_rows)

    # Apply formatting to every tab
    sheet_meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for s in sheet_meta.get("sheets", []):
        sn = s["properties"]["title"]
        try:
            formatter.apply_formatting(sheet_id, sheet_name=sn)
        except Exception as e:
            print(f"  Formatting warning ({sn}): {e}")

    print("\n" + "=" * 60)
    print("RUN COMPLETE")
    print(f"Sheet : {title}")
    print(f"Total : {len(items)} internships across {len(all_tabs)} tabs")
    print(f"URL   : https://docs.google.com/spreadsheets/d/{sheet_id}")
    print("=" * 60)
    return sheet_id


if __name__ == "__main__":
    print("=" * 60)
    print("Bangalore + Remote Tech Internship Run")
    print("Roles : Frontend, Backend, Full Stack, AI/ML, AI Automation,")
    print("        AI UGC/Content, Founder's Office, Growth, BizDev,")
    print("        Product, Ops, SDE, DevOps, Mobile + related")
    print("Location: Bangalore (on-site) OR Remote (India-based)")
    print(f"Target  : {TARGET_COUNT} internships | Separate tab per role")
    print("=" * 60)

    items = scrape_and_process()
    if items:
        create_fresh_sheet_and_publish(items)
    else:
        print("No matching internships found. Try again later.")
