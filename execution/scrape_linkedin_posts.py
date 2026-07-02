"""
scrape_linkedin_posts.py
-------------------------
Scrapes LinkedIn Posts for internship/job hiring announcements via Apify.

Primary Actor: curious_coder/linkedin-post-scraper
Fallback: Apify official "Scrape LinkedIn posts" template

Outputs:
    .tmp/linkedin_posts_raw.json   - Raw API response
    .tmp/linkedin_posts_clean.json - Filtered, schema-compliant records
"""

import os
import json
import re
import concurrent.futures
from datetime import datetime, timedelta
from apify_client import ApifyClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
TMP_DIR = ".tmp"
RAW_OUTPUT = os.path.join(TMP_DIR, "linkedin_posts_raw.json")
CLEAN_OUTPUT = os.path.join(TMP_DIR, "linkedin_posts_clean.json")

# Filter thresholds
MAX_HOURS_OLD = 96  # Max 4 days old per user request
PREFERRED_HOURS = 24  # Soft preference
MIN_HIRING_SIGNALS = 1  # Relaxed to 1 signal

# Apify actors (user-specified with correct schema)
PRIMARY_ACTOR = "supreme_coder/linkedin-post"  # User-specified
FALLBACK_ACTOR = "apimaestro/linkedin-posts-search-scraper-no-cookies"  # Backup

# Hiring intent keywords
ROLE_KEYWORDS = ["hiring", "looking for", "opening", "position", "opportunity", "vacancy", "recruit"]
ROLE_TYPES = ["intern", "internship", "job", "fresher", "trainee", "associate", "entry level"]
ACTION_WORDS = ["apply", "dm", "send resume", "share cv", "drop your resume", "send your cv", "reach out", "contact"]
URGENCY_WORDS = ["immediate", "urgent", "asap", "starting soon", "immediate joining", "walk-in"]
CONTACT_PATTERNS = [r"[\w\.-]+@[\w\.-]+", r"forms\.gle", r"bit\.ly", r"linkedin\.com/in/", r"comment below"]


def _safe_int(val) -> int:
    if isinstance(val, list): return len(val)
    if isinstance(val, dict): return val.get("count", 0) or 0
    try: return int(val) if val else 0
    except (ValueError, TypeError): return 0


def ensure_tmp_dir():
    """Ensure .tmp directory exists."""
    os.makedirs(TMP_DIR, exist_ok=True)


def parse_posted_time(posted_str: str, timestamp: int | None = None) -> int | None:
    """
    Parse LinkedIn's time to hours old.
    Handles: ISO dates, Unix timestamps, and relative time strings.
    Returns None if unparseable.
    """
    # Priority 1: Use timestamp if provided (most accurate)
    if timestamp:
        try:
            posted_dt = datetime.fromtimestamp(timestamp / 1000)  # ms to seconds
            hours_old = (datetime.now() - posted_dt).total_seconds() / 3600
            return int(hours_old)
        except:
            pass
    
    if not posted_str:
        return None
    
    # Priority 2: Try ISO date format (e.g., "2026-01-25T10:30:00.000Z")
    try:
        # Handle various ISO formats
        posted_str_clean = posted_str.replace("Z", "+00:00")
        if "T" in posted_str:
            posted_dt = datetime.fromisoformat(posted_str_clean.split("+")[0])
            hours_old = (datetime.now() - posted_dt).total_seconds() / 3600
            return int(hours_old)
    except:
        pass
    
    # Priority 3: Parse relative time strings
    posted_lower = posted_str.lower().strip()
    
    # Hours
    hours_match = re.search(r"(\d+)\s*h(our)?", posted_lower)
    if hours_match:
        return int(hours_match.group(1))
    
    # Minutes
    minutes_match = re.search(r"(\d+)\s*m(in)?", posted_lower)
    if minutes_match:
        return 0
    
    # Days
    days_match = re.search(r"(\d+)\s*d(ay)?", posted_lower)
    if days_match:
        return int(days_match.group(1)) * 24
    
    # Weeks
    weeks_match = re.search(r"(\d+)\s*w(eek)?", posted_lower)
    if weeks_match:
        return int(weeks_match.group(1)) * 24 * 7
    
    # Months (treat as very old)
    months_match = re.search(r"(\d+)\s*mo(nth)?", posted_lower)
    if months_match:
        return int(months_match.group(1)) * 24 * 30
    
    # Just now
    if "just" in posted_lower or "now" in posted_lower:
        return 0
    
    return None


def _normalize_company(name: str) -> str:
    """Normalize company name for deduplication â€” strips suffixes and spaces."""
    import re as _re
    n = name.lower().strip()
    # Remove common corporate suffixes
    n = _re.sub(r'\b(inc\.?|pvt\.?|ltd\.?|llp|llc|corp\.?|limited|private|technologies|tech|solutions|services|group|global|india)\b', '', n)
    # Collapse whitespace and non-alphanumeric chars
    n = _re.sub(r'[^a-z0-9]', '', n)
    return n


def _std_role_key(role: str) -> str:
    """Map a role string to a broad category key for cross-query deduplication."""
    r = role.lower()
    for cat, kws in [
        ("software",  ["software", "sde", "developer", "frontend", "backend", "full stack", "web", "ios", "android"]),
        ("data",      ["data", "machine learning", "ml", "ai", "analytics", "scientist"]),
        ("product",   ["product", "apm"]),
        ("marketing", ["marketing", "seo", "social media", "content"]),
        ("design",    ["design", "ui", "ux", "graphic", "video", "animation"]),
        ("finance",   ["finance", "audit", "accounting", "ca "]),
        ("sales",     ["sales", "business development", "bd"]),
        ("hr",        ["hr", "human resources", "talent", "recruitment"]),
        ("strategy",  ["founder", "generalist", "chief of staff", "operations", "strategy"]),
        ("legal",     ["law", "legal", "compliance"]),
        ("research",  ["research"]),
    ]:
        if any(k in r for k in kws):
            return cat
    return r[:20]


def detect_hiring_signals(text: str) -> list:
    """
    Detect hiring intent signals in post text.
    Returns list of matched signal categories.
    """
    if not text:
        return []
    
    text_lower = text.lower()
    signals = []
    
    # Check role keywords
    if any(kw in text_lower for kw in ROLE_KEYWORDS):
        signals.append("role_keyword")
    
    # Check role types
    if any(rt in text_lower for rt in ROLE_TYPES):
        signals.append("role_type")
    
    # Check action words
    if any(aw in text_lower for aw in ACTION_WORDS):
        signals.append("action_word")
    
    # Check urgency
    if any(uw in text_lower for uw in URGENCY_WORDS):
        signals.append("urgency")
    
    # Check contact patterns
    for pattern in CONTACT_PATTERNS:
        if re.search(pattern, text_lower):
            signals.append("contact_method")
            break
    
    return signals


def extract_role(text: str) -> str:
    """
    Extract the specific role being hired from post text.
    Returns the most specific role found or 'Internship' as fallback.
    """
    if not text:
        return "Internship"
    
    text_lower = text.lower()
    
    # Specific role patterns (most specific first)
    role_patterns = [
        # Tech roles
        (r"(software|sde|backend|frontend|full[- ]?stack|web|app|mobile|ios|android)\s*(developer|engineer|dev|intern)", "Software Developer Intern"),
        (r"(data\s*(science|scientist|analyst|analytics|engineer))", "Data Science Intern"),
        (r"(machine\s*learning|ml|ai|artificial\s*intelligence)\s*(engineer|intern)?", "ML/AI Intern"),
        (r"(devops|cloud|aws|azure|gcp)\s*(engineer|intern)?", "DevOps/Cloud Intern"),
        (r"(cyber\s*security|security|infosec)", "Security Intern"),
        (r"(qa|quality|test|testing)\s*(engineer|analyst|intern)?", "QA/Testing Intern"),
        
        # Business roles
        (r"(business\s*(analyst|development|dev)|bd)\s*(intern)?", "Business Development Intern"),
        (r"(product\s*(manager|management|owner)|pm)\s*(intern)?", "Product Management Intern"),
        (r"(project\s*(manager|management|coordinator))", "Project Management Intern"),
        (r"(operations|ops)\s*(intern|analyst|manager)?", "Operations Intern"),
        (r"(strategy|consulting|consultant)", "Strategy/Consulting Intern"),
        
        # Marketing & Creative
        (r"(digital\s*marketing|seo|sem|ppc|performance\s*marketing)", "Digital Marketing Intern"),
        (r"(social\s*media|smm|content\s*writer|content\s*creator)", "Social Media/Content Intern"),
        (r"(marketing)\s*(intern|executive|analyst)?", "Marketing Intern"),
        (r"(graphic\s*design|ui/ux|ux|ui|design)\s*(intern)?", "Design Intern"),
        (r"(video\s*edit|video\s*production|motion\s*graphics)", "Video/Motion Design Intern"),
        
        # Finance & Legal
        (r"(finance|financial\s*analyst|accounts|accounting)", "Finance/Accounts Intern"),
        (r"(investment\s*banking|ib\s*analyst|equity\s*research)", "Investment Banking Intern"),
        (r"(ca\s*intern|chartered\s*accountant|audit)", "CA/Audit Intern"),
        (r"(legal|law|paralegal|corporate\s*law)", "Legal Intern"),
        
        # HR & Admin
        (r"(hr|human\s*resource|talent\s*acquisition|recruitment)", "HR Intern"),
        (r"(admin|administration|office|executive\s*assistant)", "Admin Intern"),
        
        # Sales & Support
        (r"(sales|bdr|sdr|inside\s*sales)", "Sales Intern"),
        (r"(customer\s*(success|support)|client\s*relations)", "Customer Success Intern"),
        
        # Research & Education
        (r"(research\s*(intern|analyst|associate))", "Research Intern"),
        (r"(teaching|tutor|education|academic)", "Education/Teaching Intern"),
        
        # Generic fallbacks
        (r"(intern|internship|trainee|fresher)", "Internship"),
    ]
    
    for pattern, role_name in role_patterns:
        if re.search(pattern, text_lower):
            return role_name
    
    return "Internship"


def calculate_engagement_score(likes: int, comments: int, reposts: int = 0) -> int:
    """
    Calculate engagement quality score.
    """
    score = 0
    if likes and likes > 50:
        score += 1
    if comments and comments > 10:
        score += 1
    if reposts and reposts > 5:
        score += 1
    return score


def extract_emails_from_text(text: str) -> list:
    """Extract email addresses from post text using regex."""
    if not text:
        return []
    email_pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    # Filter out common false positives
    filtered = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif', '.svg'))]
    return list(set(filtered))


def extract_location_from_text(text: str) -> str:
    """Extract location from post text using regex city matching."""
    if not text:
        return ""
    text_lower = text.lower()
    
    # Indian cities list
    cities = [
        "bangalore", "bengaluru", "mumbai", "delhi", "new delhi",
        "gurgaon", "gurugram", "noida", "hyderabad", "chennai",
        "pune", "kolkata", "ahmedabad", "jaipur", "lucknow",
        "chandigarh", "indore", "kochi", "coimbatore", "nagpur",
        "bhopal", "visakhapatnam", "thiruvananthapuram", "surat",
        "vadodara", "mysore", "mangalore", "remote", "work from home",
        "wfh", "hybrid"
    ]
    
    found = []
    for city in cities:
        if city in text_lower:
            display = city.title()
            if city in ["remote", "work from home", "wfh"]:
                display = "Remote"
            elif city == "hybrid":
                display = "Hybrid"
            elif city == "gurgaon" or city == "gurugram":
                display = "Gurgaon"
            elif city == "bengaluru":
                display = "Bangalore"
            elif city == "new delhi":
                display = "New Delhi"
            if display not in found:
                found.append(display)
    
    return ", ".join(found[:2]) if found else ""


def extract_apply_link(text: str) -> str:
    """Extract apply/form URL from post text."""
    if not text:
        return ""
    # Match URLs, prefer forms/apply links
    urls = re.findall(r'(https?://[^\s<>"\)]+)', text)
    # Prioritize apply/form links
    for url in urls:
        if any(kw in url.lower() for kw in ['form', 'apply', 'career', 'job', 'hire', 'lnkd.in']):
            return url
    return urls[0] if urls else ""


def filter_posts(posts: list) -> list:
    """
    HYBRID EXTRACTION: Apify metadata + regex.
    NO filtering â€” all posts pass through.
    Extracts: company (from author), role, location, email, apply_link via regex.
    """
    clean_posts = []
    
    for post in posts:
        # --- APIFY STRUCTURED DATA ---
        author_name = post.get("authorName") or post.get("author", {}).get("name") or ""
        author_headline = post.get("authorHeadline") or post.get("author", {}).get("headline") or ""
        # Company: try author's company field first, then parse from headline
        author_company = post.get("authorCompany") or post.get("author", {}).get("company") or ""
        
        # If no explicit company field, try to extract from author headline
        # Headlines often look like: "HR Manager at Google" or "Founder | XYZ Corp"
        if not author_company and author_headline:
            # Try "at Company" pattern
            at_match = re.search(r'\bat\s+([A-Z][\w\s&\.]+?)(?:\s*[|Â·â€¢\-â€“]|$)', author_headline)
            if at_match:
                author_company = at_match.group(1).strip()
            else:
                # Try "Role | Company" or "Role - Company" pattern
                sep_match = re.search(r'[|Â·â€¢\-â€“]\s*([A-Z][\w\s&\.]+?)(?:\s*[|Â·â€¢\-â€“]|$)', author_headline)
                if sep_match:
                    candidate = sep_match.group(1).strip()
                    # Make sure it's not a role description
                    role_words = ['intern', 'manager', 'director', 'head', 'lead', 'officer', 'analyst']
                    if not any(rw in candidate.lower() for rw in role_words):
                        author_company = candidate
        
        # Fallback: use author name if still no company
        company = author_company if author_company else author_name
        
        post_text = post.get("text") or post.get("postText") or post.get("content") or ""
        posted_time = post.get("postedTime") or post.get("publishedAt") or post.get("time") or ""
        likes = post.get("likes") or post.get("likeCount") or post.get("numLikes") or 0
        comments = post.get("comments") or post.get("commentCount") or post.get("numComments") or 0
        reposts = post.get("reposts") or post.get("repostCount") or 0
        url = post.get("url") or post.get("postUrl") or post.get("link") or ""
        
        likes = _safe_int(likes)
        comments = _safe_int(comments)
        reposts = _safe_int(reposts)
        
        # --- REGEX EXTRACTION ---
        role = extract_role(post_text)
        location = extract_location_from_text(post_text)
        emails = extract_emails_from_text(post_text)
        apply_link = extract_apply_link(post_text)
        
        # Work type
        text_lower = post_text.lower()
        work_type = ""
        if "part-time" in text_lower or "part time" in text_lower:
            work_type = "Part-time"
        elif "full-time" in text_lower or "full time" in text_lower:
            work_type = "Full-time"
        
        # Hiring signals (for scoring, not filtering)
        hiring_signals = detect_hiring_signals(post_text)
        engagement_score = calculate_engagement_score(likes, comments, reposts)
        
        # Freshness scoring
        timestamp = post.get("postedAtTimestamp") or post.get("timestamp")
        iso_date = post.get("postedAtISO") or post.get("publishedAt") or posted_time
        hours_old = parse_posted_time(iso_date, timestamp)
        freshness_bonus = 1 if (hours_old is not None and hours_old <= PREFERRED_HOURS) else 0
        is_stale = hours_old is not None and hours_old > 12 and engagement_score == 0
        
        # Build clean record â€” ALL posts pass through
        clean_posts.append({
            "author_name": author_name,
            "author_headline": author_headline,
            "post_text": post_text[:500] + "..." if len(post_text) > 500 else post_text,
            "posted_time": posted_time,
            "likes": likes,
            "comments": comments,
            "url": url,
            "role": role,
            "company": company,
            "location": location,
            "contact_email": ", ".join(emails) if emails else "",
            "apply_link": apply_link,
            "work_type": work_type,
            "hiring_signals": hiring_signals,
            "engagement_score": engagement_score,
            "freshness_bonus": freshness_bonus,
            "is_stale": is_stale
        })
    
    # Sort by: freshness bonus + engagement score (descending)
    clean_posts.sort(key=lambda x: (x["freshness_bonus"], x["engagement_score"]), reverse=True)
    
    return clean_posts


def run_apify_actor(actor_id: str, search_params: dict) -> list:
    """
    Run an Apify actor and return results.
    """
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        raise EnvironmentError("APIFY_API_TOKEN not set in environment")
    
    client = ApifyClient(api_token)
    
    print(f"Running actor: {actor_id}")
    run = client.actor(actor_id).call(run_input=search_params)
    
    # CHECK FOR ACTOR FAILURE
    status = run.get("status")
    if status != "SUCCEEDED":
        print(f"   âš ï¸ Actor {actor_id} run {run.get('id')} ended with status: {status}")
        # Even if failed, some items might have been saved to the dataset
        # But for reliability, we should treat it as a failure if we got 0 items
    
    # Fetch results from dataset
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Actor returned {len(items)} items")
    
    if not items and status != "SUCCEEDED":
        raise Exception(f"Apify actor {actor_id} failed with status {status}")
        
    return items


def _pre_filter_posts(raw_posts: list, seen_urls: set) -> list:
    """Apply pre-LLM filters: dedup, spam, story, hiring-intent, time."""
    _PRE_COMPANY_BLACKLIST = ["gao group", "gaotek", "gao tek"]
    _PRE_SCAM_PATTERNS = [
        "registration fee", "reg fee", "training fee", "training charges",
        "security deposit", "caution money", "certification fee",
        "pay to join", "investment required", "typing job",
        "data entry job", "form filling job", "copy paste job",
        "earn daily", "easy money", "100 genuine", "guaranteed income",
        "whatsapp to register", "simple typing", "home based typing",
    ]
    story_keywords = [
        "my journey", "wrapped up my time", "excited to announce", "officially a",
        "vibecoding", "employee market hai", "from learning to earning",
        "i am looking for", "i'm looking for", "seeking a", "seeking an", "open to work",
    ]
    hiring_keywords = [
        "hiring", "looking for", "apply", "opportunity", "openings",
        "interns required", "join our team", "we are expanding", "internship alert",
    ]

    passed = []
    for p in raw_posts:
        url = p.get("url") or p.get("post_url") or p.get("postUrl") or p.get("link")
        raw_text = (p.get("text") or p.get("postText") or p.get("content") or "")
        norm_text = re.sub(r'[^\w\s]', '', raw_text[:300]).lower()
        norm_text = re.sub(r'\s+', ' ', norm_text).strip()[:150]
        text_hash = hash(norm_text) if norm_text else None

        # Generic spam blocks
        if norm_text and "hiring for multiple positions" in norm_text:
            continue
        if norm_text and "apply now for internship" in norm_text and "hiring" in norm_text:
            continue

        # Company blacklist
        author_raw = (p.get("authorName") or p.get("author", {}).get("name", "") or "").lower()
        if any(bl in author_raw for bl in _PRE_COMPANY_BLACKLIST) or any(bl in norm_text[:80] for bl in _PRE_COMPANY_BLACKLIST):
            continue

        # Pre-LLM scam filter
        if any(kw in norm_text for kw in _PRE_SCAM_PATTERNS):
            continue

        # Personal story filter
        if any(kw in norm_text for kw in story_keywords):
            continue

        # Hiring intent gate
        has_hiring_intent = any(kw in norm_text for kw in hiring_keywords)
        if not has_hiring_intent and "intern" not in norm_text:
            continue

        # Time filter â€” reject if clearly > 4 days old
        posted_time = str(p.get("postedTime") or p.get("publishedAt") or p.get("time") or "").lower().strip()
        if "w" in posted_time or "mo" in posted_time or "yr" in posted_time or "year" in posted_time or "month" in posted_time or "week" in posted_time:
            continue
        days_match = re.search(r"(\d+)\s*d", posted_time)
        if days_match and int(days_match.group(1)) > 4:
            continue

        # URL/text dedup (thread-safe read â€” caller must not mutate seen_urls concurrently)
        if text_hash and text_hash in seen_urls:
            continue
        if url and url in seen_urls:
            continue

        passed.append((p, url, text_hash))

    return passed


def _scrape_one_query(args):
    """Scrape a single query â€” designed to run in a thread."""
    query, run_input = args
    try:
        posts = run_apify_actor(PRIMARY_ACTOR, run_input)
        return query, posts
    except Exception as e:
        print(f"   âŒ Primary scraper failed for query '{query[:60]}': {e}")
        try:
            posts = run_apify_actor(FALLBACK_ACTOR, run_input)
            return query, posts
        except Exception as e2:
            print(f"   âŒ Fallback also failed: {e2}")
            return query, []


def main():
    """
    Main execution flow (Parallel Mode):
    1. Launch all Apify scrape queries IN PARALLEL (5 workers).
    2. Collect + dedup all raw posts as they arrive.
    3. Run one big concurrent LLM pass on all pre-filtered posts.
    4. Apply post-LLM filters and save output.
    """
    ensure_tmp_dir()

    TARGET_VERIFIED = 120  # Aim for 120 to absorb duplicates and reach 105 net-new in sheet
    IS_TOPUP = False
    verified_posts = []
    seen_urls = set()
    seen_authors = set()       # Prevent recruiter spam from same user
    seen_company_roles = set() # Cross-query dedup: prevent same company+role from two queries

    # Pre-load existing sheet dedup keys so we skip already-published internships
    existing_keys_file = os.path.join(TMP_DIR, "existing_sheet_keys.json")
    if os.path.exists(existing_keys_file):
        try:
            with open(existing_keys_file, "r", encoding="utf-8") as f:
                existing_keys = json.load(f)
            for key in existing_keys:
                if key.startswith("http"):
                    seen_urls.add(key)
                else:
                    seen_company_roles.add(key)
            print(f"âœ… Pre-loaded {len(existing_keys)} existing sheet keys (URLs + company:role) to avoid duplicates")
        except Exception as e:
            print(f"âš ï¸ Could not load existing sheet keys: {e}")

    # Topup mode: fill only the deficit from a prior partial run
    topup_file = os.path.join(TMP_DIR, "scrape_topup.json")
    if os.path.exists(topup_file):
        try:
            with open(topup_file, "r") as f:
                topup_cfg = json.load(f)
            TARGET_VERIFIED = topup_cfg.get("target", 30)
            IS_TOPUP = True
            print(f"ðŸ”„ TOPUP MODE: targeting {TARGET_VERIFIED} additional posts to fill deficit")
            # Load previously scraped posts so we don't re-find the same ones
            if os.path.exists(CLEAN_OUTPUT):
                with open(CLEAN_OUTPUT, "r", encoding="utf-8") as f:
                    prev_posts = json.load(f)
                for p in prev_posts:
                    if p.get("url"):
                        seen_urls.add(p["url"])
                    cr = f"{_normalize_company(p.get('company',''))}:{_std_role_key(p.get('title','') or p.get('role',''))}"
                    seen_company_roles.add(cr)
                print(f"   Loaded {len(prev_posts)} previous posts into seen sets")
        except Exception as e:
            print(f"âš ï¸ Could not load topup config: {e}")

    # â”€â”€ Search queries (10 field-specific) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    search_queries_count = 10
    MAX_PER_QUERY = (TARGET_VERIFIED // search_queries_count) + 1  # ~13 per query

    search_queries = [
        "(software intern) OR (sde intern) OR (full stack intern) OR (backend intern) OR (frontend intern) OR (web developer intern)",
        "(data science intern) OR (ml intern) OR (machine learning intern) OR (ai intern) OR (data engineer intern) OR (data analyst intern)",
        "(product management intern) OR (apm intern) OR (product analyst intern) OR (associate product manager intern)",
        "(founder's office intern) OR (generalist intern) OR (chief of staff intern) OR (strategy intern) OR (operations intern)",
        "(business development intern) OR (sales intern) OR (bd intern) OR (inside sales intern) OR (growth intern)",
        "(digital marketing intern) OR (marketing intern) OR (seo intern) OR (performance marketing intern) OR (social media intern)",
        "(video editing intern) OR (content writing intern) OR (copywriting intern) OR (graphic design intern) OR (vfx intern)",
        "(ui ux intern) OR (product design intern) OR (visual design intern)",
        "(finance intern) OR (investment banking intern) OR (vc intern) OR (audit intern) OR (consulting intern)",
        "(hr intern india) OR (talent acquisition intern) OR (human resources intern) OR (law intern) OR (compliance intern)",
    ]
    import random
    random.shuffle(search_queries)

    print("="*60)
    print(f"LINKEDIN POSTS SCRAPER - PARALLEL MODE")
    print(f"Target: {TARGET_VERIFIED} verified | Max per query: {MAX_PER_QUERY}")
    print("="*60)

    # â”€â”€ Configure LLM â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        import llm_post_analyzer
    except ModuleNotFoundError:
        import execution.llm_post_analyzer as llm_post_analyzer
    llm_post_analyzer.configure_llm()
    print(f"âœ… LLM: {llm_post_analyzer.PROVIDER.title()} ({llm_post_analyzer.MODEL})")
    filter_posts_with_llm = llm_post_analyzer.filter_posts_with_llm
    use_llm = llm_post_analyzer.PROVIDER != "none"

    # â”€â”€ PHASE 1: Parallel Apify scraping â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # All 10 queries run concurrently (5 workers) instead of sequentially.
    # Apify calls are pure I/O waits (1-3 min each) â€” threads eliminate that wait.
    query_inputs = []
    for query in search_queries:
        search_url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?datePosted=%22past-24h%22&keywords={query.replace(' ', '%20')}"
            f"&origin=FACETED_SEARCH"
        )
        query_inputs.append((query, {"urls": [search_url], "limitPerSource": 40}))

    print(f"\n[PHASE 1] Launching {len(query_inputs)} Apify scrapes in parallel (5 workers)...")
    all_raw_by_query = {}  # query â†’ list of raw posts
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(_scrape_one_query, qi): qi[0] for qi in query_inputs}
        for future in concurrent.futures.as_completed(future_map):
            query_str = future_map[future]
            try:
                _, posts = future.result()
                all_raw_by_query[query_str] = posts
                print(f"   âœ… '{query_str[:60]}' â†’ {len(posts)} raw posts")
            except Exception as e:
                print(f"   âŒ Query failed: {e}")
                all_raw_by_query[query_str] = []

    total_raw = sum(len(v) for v in all_raw_by_query.values())
    print(f"\n[PHASE 1 DONE] {total_raw} raw posts collected across all queries.")

    # â”€â”€ PHASE 2: Dedup + pre-filter (single-threaded, fast) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[PHASE 2] Deduplicating and pre-filtering...")
    all_to_llm = []
    for query_str, raw_posts in all_raw_by_query.items():
        if not raw_posts:
            continue
        passed = _pre_filter_posts(raw_posts, seen_urls)
        # Commit seen hashes for this query's batch
        query_passed = []
        for p, url, text_hash in passed:
            if url and url not in seen_urls:
                seen_urls.add(url)
                if text_hash:
                    seen_urls.add(text_hash)
                query_passed.append(p)
            elif not url and text_hash and text_hash not in seen_urls:
                seen_urls.add(text_hash)
                query_passed.append(p)
        # Per-query cap to preserve field diversity
        if len(query_passed) > MAX_PER_QUERY * 3:
            query_passed = query_passed[:MAX_PER_QUERY * 3]
        print(f"   '{query_str[:50]}' â†’ {len(query_passed)} posts after pre-filter")
        all_to_llm.extend(query_passed)

    print(f"\n[PHASE 2 DONE] {len(all_to_llm)} posts queued for LLM.")

    # â”€â”€ PHASE 3: One big concurrent LLM pass â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[PHASE 3] Running LLM analysis on {len(all_to_llm)} posts (10 workers)...")
    llm_results = filter_posts_with_llm(all_to_llm) if use_llm else all_to_llm

    # â”€â”€ PHASE 4: Post-LLM filters + build clean records â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[PHASE 4] Applying post-LLM filters to {len(llm_results)} results...")
    _INDIA_CITIES = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi",
        "gurgaon", "gurugram", "noida", "hyderabad", "chennai", "pune",
        "kolkata", "ahmedabad", "jaipur", "lucknow", "chandigarh", "indore",
        "kochi", "coimbatore", "nagpur", "bhopal", "visakhapatnam",
        "thiruvananthapuram", "surat", "vadodara", "mysore", "mangalore",
        "pan india", "wfh", "work from home",
    ]
    _OUTSIDE_INDICATORS = [
        "usa", "uk", "london", "new york", "san francisco", "los angeles",
        "dubai", "uae", "australia", "canada", "germany", "singapore",
        "hong kong", "europe", "united states", "united kingdom", "korea",
        "japan", "china", "malaysia", "netherlands", "france", "italy",
        "toronto", "sydney", "berlin", "amsterdam", "paris", "seoul",
        "riyadh", "kuwait", "qatar", "bahrain", "oman",
    ]
    _india_text_kw = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi",
        "hyderabad", "pune", "noida", "gurgaon", "chennai",
        "kolkata", "ahmedabad", "jaipur", "pan india",
        "indian students", "for india", "in india", "indian candidates",
    ]

    if use_llm:
        for post in llm_results:
            analysis = post.get("llm_analysis", {})
            if isinstance(analysis, list):
                analysis = analysis[0] if analysis else {}

            llm_company = analysis.get("company") or ""
            llm_roles = analysis.get("roles", [])
            llm_location = analysis.get("location") or ""
            llm_email = analysis.get("contact_email") or ""
            llm_apply_link = analysis.get("apply_link") or ""
            llm_work_type = analysis.get("work_type") or ""
            llm_formatted_desc = analysis.get("formatted_description") or ""

            author_name = post.get("authorName") or post.get("author", {}).get("name", "") or "Recruiter"
            author_headline = post.get("authorHeadline") or post.get("author", {}).get("headline", "") or ""

            if author_name != "Recruiter" and author_name in seen_authors:
                continue
            seen_authors.add(author_name)

            final_company = llm_company if llm_company not in [None, "", "null", "Unknown"] else ""
            if not final_company:
                final_company = post.get("authorCompany") or post.get("author", {}).get("company", "") or ""
            if not final_company:
                at_match = re.search(r'\bat\s+([A-Z][\w\s&\.]+?)(?:\s*[|·•\-–]|$)', author_headline)
                if at_match:
                    final_company = at_match.group(1).strip()
            if not final_company:
                final_company = author_name

            final_role = llm_roles[0] if llm_roles and llm_roles[0] not in [None, ""] else "Internship"
            final_location = llm_location if llm_location not in [None, "", "null", "Unknown"] else ""

            post_text = post.get("text") or post.get("postText") or post.get("content") or ""
            url = post.get("url") or post.get("postUrl") or post.get("link") or ""
            loc_lower = final_location.lower()
            text_lower = post_text.lower()

            is_outside = any(kw in loc_lower for kw in _OUTSIDE_INDICATORS)
            if is_outside and "india" not in loc_lower:
                print(f"    ❌ Skipped (international): {final_location}")
                continue

            is_india_loc = any(kw in loc_lower for kw in _INDIA_CITIES)
            is_remote_only = "remote" in loc_lower and not is_india_loc

            if is_remote_only:
                if not any(kw in text_lower for kw in _india_text_kw):
                    print(f"    ❌ Skipped (Remote, no India context): {final_company}")
                    continue
            elif not is_india_loc and "remote" not in loc_lower:
                if not any(kw in text_lower for kw in _india_text_kw):
                    print(f"    ❌ Skipped (no India context): {final_location or 'unknown'}")
                    continue

            # Resolve an ABSOLUTE posted date so the website can show real
            # freshness (not the time the row was added to the sheet).
            _posted_iso = post.get("postedAtISO") or post.get("publishedAt") or ""
            _posted_ts = post.get("postedAtTimestamp") or post.get("timestamp")
            _hours_old = parse_posted_time(_posted_iso or str(post.get("postedTime") or ""), _posted_ts)
            posted_date = (
                (datetime.now() - timedelta(hours=_hours_old)).strftime("%Y-%m-%d")
                if _hours_old is not None else ""
            )

            clean_post = {
                "author_name": author_name,
                "author_headline": author_headline,
                "post_text": post_text[:500],
                "posted_time": post.get("postedTime") or post.get("postedAtISO") or "",
                "posted_date": posted_date,
                "likes": post.get("likes") or 0,
                "comments": post.get("comments") or 0,
                "url": url,
                "title": final_role,
                "type": analysis.get("type") or "",
                "timing": analysis.get("timing") or "",
                "description": llm_formatted_desc if len(llm_formatted_desc) > 20 else post_text[:5000],
                "stipend": analysis.get("stipend") or "",
                "duration": analysis.get("duration") or "",
                "experience": analysis.get("experience") or "",
                "location": final_location,
                "deadline": analysis.get("deadline") or "",
                "tags": analysis.get("tags") or [],
                "hiringOrganization": final_company,
                "contact_email": llm_email,
                "apply_link": llm_apply_link,
                "role": final_role,
                "company": final_company,
                "work_type": llm_work_type,
                "hiring_signals": ["llm_extracted"],
                "engagement_score": 1,
                "freshness_bonus": 1,
                "is_stale": False,
            }

            _cr_key = f"{_normalize_company(final_company)}:{_std_role_key(final_role)}"
            if _cr_key in seen_company_roles:
                continue
            seen_company_roles.add(_cr_key)

            verified_posts.append(clean_post)
    else:
        verified_posts.extend(filter_posts(all_to_llm))

    if len(verified_posts) < 10:
        print("\n⚠️ Warning: Very few verified posts found. Relaxing filters might be needed.")

    # Save output — in topup mode, merge with existing posts
    if IS_TOPUP and os.path.exists(CLEAN_OUTPUT):
        try:
            with open(CLEAN_OUTPUT, "r", encoding="utf-8") as f:
                prev_posts = json.load(f)
            verified_posts = prev_posts + verified_posts
            print(f"\nTopup merged: {len(prev_posts)} existing + {len(verified_posts) - len(prev_posts)} new = {len(verified_posts)} total")
        except Exception as e:
            print(f"⚠️ Could not merge with existing posts: {e}")

    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(verified_posts, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved {len(verified_posts)} posts → {CLEAN_OUTPUT}")

    # Record real run metrics so publish_to_sheets can surface honest stats
    # (scanned vs. verified) on the website's /api/stats endpoint.
    verified_count = len(verified_posts)
    metrics = {
        "scanned": total_raw,
        "verified": verified_count,
        "rejected": max(0, total_raw - verified_count),
    }
    try:
        with open(os.path.join(TMP_DIR, "scrape_metrics.json"), "w") as f:
            json.dump(metrics, f)
        print(f"📊 Run metrics: scanned={total_raw} verified={verified_count} "
              f"rejected={metrics['rejected']}")
    except Exception as e:
        print(f"⚠️ Could not write scrape metrics: {e}")

    return verified_posts



if __name__ == "__main__":
    results = main()
    print(f"\nTotal filtered posts: {len(results)}")

    if results:
        print("\nTop 3 posts:")
        for i, post in enumerate(results[:3], 1):
            print(f"  {i}. {post.get('hiringOrganization','?')} — {post.get('title','?')}")

    import os
    os._exit(0)