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
import sys

try:
    from execution.hunt_core.network import enable_system_ca
except ImportError:
    from hunt_core.network import enable_system_ca

enable_system_ca()
import json
import re
import concurrent.futures
from datetime import datetime, timedelta

# UTF-8 stdout so emoji log lines survive a redirected Windows console (cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from apify_client import ApifyClient
from dotenv import load_dotenv

try:
    from execution import quality_filter, role_taxonomy
except ImportError:
    import quality_filter
    import role_taxonomy

# Load environment variables
load_dotenv()

# Constants
TMP_DIR = ".tmp"
RAW_OUTPUT = os.path.join(TMP_DIR, "linkedin_posts_raw.json")
CLEAN_OUTPUT = os.path.join(TMP_DIR, "linkedin_posts_clean.json")

# Filter thresholds. Two windows now: abundant role tracks stay tight, scarce
# ones (founder's office, forward-deployed, AI automation, product eng,
# business ops) widen to 7 days. Those roles post rarely enough that a 24h/4d
# window returned literally zero of them — see role_taxonomy.SCARCE_TRACKS.
# Dedup already prevents re-publishing, so the only cost is slightly older posts
# in the tracks that were previously empty.
MAX_HOURS_OLD = 96       # 4 days — abundant tracks
SCARCE_HOURS_OLD = 168   # 7 days — scarce tracks
PREFERRED_HOURS = 24  # Soft preference
MIN_HIRING_SIGNALS = 1  # Relaxed to 1 signal

# Apify actor: harvestapi/linkedin-post-search — no-cookies, 19K users, 4.9★,
# $2/1k, actively maintained. Reliable keyword post search.
# (The old primary supreme_coder/linkedin-post was dropped: it relies on a shared
#  LinkedIn account pool that returns "no available accounts found" and it was
#  under maintenance — every query came back empty.)
#
# The apimaestro fallback (used on ANY 0-result primary query, not just
# exceptions) was removed 2026-07-27 — it costs 2.5x more per result ($5/1k vs
# $2/1k), and because it fired on every empty-result query, not just failures,
# it was silently multiplying real spend on nights the primary actor simply
# had nothing for a given city/field combo. It directly contributed to an
# Apify account lockout. No fallback now — a 0-result query just stays empty.
PRIMARY_ACTOR = "harvestapi/linkedin-post-search"
HARVESTAPI_MAX_POSTS = 25       # scarce tracks — they never approach this
# Abundant tracks were truncating at 25 on every remote query (2026-08-22), so
# 40 looks right on supply grounds — but Apify bills per RESULT and the account
# is capped at $5/month, where 118 queries x 40 = 4,720 results = $9.44 in a
# SINGLE night. Cost, not supply, is the binding constraint, so this stays at
# 25 and MAX_RESULTS_PER_RUN below does the real protecting.
HARVESTAPI_MAX_POSTS_WIDE = 25

# Hard ceiling on results collected per run — the safety net that stops a run
# from eating a whole month's Apify budget. harvestapi bills ~$2 per 1k results,
# so 700 results is ~$1.40/night, the per-run figure agreed with the product
# owner on 2026-08-23. Tune via SCRAPE_MAX_RESULTS.
MAX_RESULTS_PER_RUN = int(os.getenv("SCRAPE_MAX_RESULTS", "700"))
APIFY_USD_PER_RESULT = 0.002

# Apify reserves projected spend for every QUEUED actor run, not just running
# ones, and counts that against the account's monthly cap. A 118-query fan-out
# at 8 workers spiked the reported usage to $8.29 against a $5 cap on
# 2026-08-23 and got most queries rejected with "Monthly usage hard limit
# exceeded" — while actually billing about $0.05, because rejected runs aren't
# charged. Keeping the burst small is what stops that reservation spike.
APIFY_WORKERS = int(os.getenv("SCRAPE_WORKERS", "4"))

# The budget is spent PER TRACK, not first-come-first-served. A single global
# cap would be eaten by whichever queries return fastest — and that is the
# high-volume marketing/design tracks, which would starve the scarce tracks of
# spend and rebuild the very skew role balancing exists to fix. Splitting the
# budget evenly across tracks enforces diversity at the SPEND layer, before the
# quality gate or the publish quota ever see a post.
def _per_track_budget(n_tracks):
    return max(20, MAX_RESULTS_PER_RUN // max(1, n_tracks))

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
    """Broad role category for cross-query dedup.

    Delegates to role_taxonomy so the scraper, publish_to_sheets, and the
    website API can never disagree about what kind of role something is again.
    """
    return role_taxonomy.infer_track(role)


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
        # Specific 2026 role families — MUST precede the broad tech/business
        # patterns below, which would otherwise swallow them ("Founder's Office
        # Intern" matched the generic "office" rule and came out as "Admin
        # Intern"; "AI Automation Intern" came out as "ML/AI Intern"). Mirrors
        # the ordering role_taxonomy._RULES uses for the same reason.
        (r"(founder'?s?\s*(office|associate)|chief\s*of\s*staff|entrepreneur\s*in\s*residence|business\s*generalist)", "Founder's Office Intern"),
        (r"(forward\s*deployed|solutions?\s*(engineer|architect)|implementation\s*engineer|deployment\s*engineer)", "Forward Deployed Engineer Intern"),
        (r"(ai\s*automation|automation\s*engineer|workflow\s*automation|ai\s*agent|agentic|llm\s*engineer|gen\s*ai|generative\s*ai|prompt\s*engineer)", "AI Automation Intern"),
        (r"(product\s*engineer|growth\s*engineer|gtm\s*engineer|founding\s*engineer)", "Product Engineer Intern"),
        (r"(business\s*operations|biz\s*ops|revenue\s*operations|rev\s*ops)", "Business Operations Intern"),

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


def _run_field(run, key: str, default=None):
    """Read one field off an Apify run result, whichever shape the client returns.

    apify-client hands back a plain dict on 2.x but a `Run` model object (attributes,
    snake_case, no `.get`) on 3.x. requirements.txt pinned only `apify-client>=1.0.0`,
    so Modal's image resolved a newer major than local dev and every cloud query died
    on `'Run' object has no attribute 'get'` -- while the actors still ran and BILLED.
    Reading through this helper keeps both shapes working.
    """
    if run is None:
        return default
    if isinstance(run, dict):
        return run.get(key, default)
    # Run model: defaultDatasetId -> default_dataset_id
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
    return getattr(run, snake, getattr(run, key, default))


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
    status = _run_field(run, "status")
    if status != "SUCCEEDED":
        print(f"   âš ï¸ Actor {actor_id} run {_run_field(run, 'id')} ended with status: {status}")
        # Even if failed, some items might have been saved to the dataset
        # But for reliability, we should treat it as a failure if we got 0 items
    
    # Fetch results from dataset
    dataset_id = _run_field(run, "defaultDatasetId")
    if not dataset_id:
        # The run was billed either way, so never let this degrade into a silent 0.
        raise Exception(
            f"Apify actor {actor_id} returned no dataset id "
            f"(status={status}, result type={type(run).__name__})")
    items = list(client.dataset(dataset_id).iterate_items())
    print(f"Actor returned {len(items)} items")
    
    if not items and status != "SUCCEEDED":
        raise Exception(f"Apify actor {actor_id} failed with status {status}")
        
    return items


def _pre_filter_posts(raw_posts: list, seen_urls: set, max_days: int = 4) -> list:
    """Apply pre-LLM filters: dedup, spam, story, hiring-intent, time.

    `max_days` is track-aware: 4 for abundant tracks, 7 for scarce ones. Without
    this the widened scrape window for scarce tracks would be thrown away one
    stage later, right here.
    """
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

        # Aggregator / reposter / paid-mentorship pre-cut (cheap, saves LLM cost).
        # Uses raw text (not norm_text) so URL/emoji patterns survive.
        _author_name = p.get("authorName") or (p.get("author", {}) or {}).get("name", "") or ""
        _author_headline = p.get("authorHeadline") or (p.get("author", {}) or {}).get("headline", "") or ""
        _is_agg, _ = quality_filter.is_aggregator_post(_author_name, _author_headline, raw_text)
        if _is_agg:
            continue

        # Hiring intent gate — scan the FULL post text (not just the first 150
        # chars) so a genuine post isn't dropped when "intern"/"hiring" appears
        # lower down. The LLM gate does the real screening; keep this permissive.
        _full_lower = raw_text.lower()
        has_hiring_intent = any(kw in _full_lower for kw in hiring_keywords)
        if not has_hiring_intent and "intern" not in _full_lower:
            continue

        # Time filter — reject if older than this track's window
        posted_time = str(p.get("postedTime") or p.get("publishedAt") or p.get("time") or "").lower().strip()
        if "mo" in posted_time or "yr" in posted_time or "year" in posted_time or "month" in posted_time:
            continue
        weeks_match = re.search(r"(\d+)\s*w", posted_time)
        if weeks_match and int(weeks_match.group(1)) * 7 > max_days:
            continue
        days_match = re.search(r"(\d+)\s*d", posted_time)
        if days_match and int(days_match.group(1)) > max_days:
            continue

        # URL/text dedup (thread-safe read â€” caller must not mutate seen_urls concurrently)
        if text_hash and text_hash in seen_urls:
            continue
        if url and url in seen_urls:
            continue

        passed.append((p, url, text_hash))

    return passed


def _build_actor_input(actor_id, query, url_input, scarce=False):
    """Build the run-input each actor expects. harvestapi uses `searchQueries`;
    url-based actors (apimaestro/legacy) use the LinkedIn search URL input."""
    if actor_id.startswith("harvestapi/"):
        # Freshness window. Abundant tracks stay at 24h for nightly runs;
        # scarce tracks widen to 7d because a 24h window returns nothing for
        # them. SCRAPE_POSTED_LIMIT overrides both for a catch-up run. The
        # PHASE-2 time filter trims to the matching MAX_HOURS_OLD /
        # SCARCE_HOURS_OLD bound.
        # harvestapi validates this field against a fixed vocabulary:
        # any | 1h | 24h | week | month | 3months | 6months | year.
        # "7d" is REJECTED ("Input is not valid") and the whole query fails, so
        # the 7-day window for scarce tracks must be spelled "week".
        default_limit = "week" if scarce else "24h"
        posted_limit = os.getenv("SCRAPE_POSTED_LIMIT", default_limit)
        return {
            "searchQueries": [query],
            # Scarce tracks rarely fill even the base cap; abundant ones were
            # hitting exactly 25 on every remote query last run (truncated
            # supply), so give them headroom.
            "maxPosts": HARVESTAPI_MAX_POSTS if scarce else HARVESTAPI_MAX_POSTS_WIDE,
            "postedLimit": posted_limit,
            "sortBy": "date",
        }
    return url_input


def _normalize_harvestapi_item(it):
    """Map harvestapi's nested output to the flat schema the rest of the
    pipeline reads (text/url/authorName/authorHeadline/postedAt*)."""
    author = it.get("author") or {}
    posted = it.get("postedAt") or {}
    eng = it.get("engagement") or {}
    return {
        "authorName": author.get("name") or "",
        "authorHeadline": author.get("info") or "",
        "authorCompany": "",  # not provided for profile authors; resolved later
        "text": it.get("content") or "",
        "url": it.get("linkedinUrl") or it.get("shareLinkedinUrl") or "",
        "postedTime": posted.get("postedAgoShort") or "",
        "postedAtISO": posted.get("date") or "",
        "postedAtTimestamp": posted.get("timestamp"),
        "likes": eng.get("likes") or eng.get("reactions") or 0,
        "comments": eng.get("comments") or 0,
    }


def _normalize_actor_items(actor_id, items):
    if actor_id.startswith("harvestapi/"):
        return [_normalize_harvestapi_item(it) for it in items]
    return items  # url-based actors already emit fields the pipeline reads


def check_apify_budget():
    """Return (ok, message). Reads the account's monthly usage before spending.

    Without this, an exhausted cap surfaces as 118 identical
    "Monthly usage hard limit exceeded" failures buried in the log and a run
    that silently publishes nothing — which is exactly how a real run failed on
    2026-08-23. One clear line up front beats 118 confusing ones.
    """
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        return True, "no token to check (will fail later if truly missing)"
    try:
        import requests
        r = requests.get("https://api.apify.com/v2/users/me/limits",
                         headers={"Authorization": f"Bearer {token}"}, timeout=20)
        d = r.json().get("data", {})
        used = float(d.get("current", {}).get("monthlyUsageUsd") or 0)
        cap = float(d.get("limits", {}).get("maxMonthlyUsageUsd") or 0)
        if not cap:
            return True, "no monthly cap set"
        remaining = cap - used
        affordable = int(remaining / 0.002)  # harvestapi bills ~$2 / 1k results
        msg = (f"Apify budget: ${used:.2f} / ${cap:.2f} used, ${remaining:.2f} left "
               f"(~{affordable} results)")
        if remaining <= 0.10:
            return False, msg + " — EXHAUSTED, skipping scrape to avoid 100+ failures"
        return True, msg
    except Exception as e:
        return True, f"budget check failed ({e}) — proceeding"


def _scrape_one_query(args):
    """Scrape a single query - designed to run in a thread.

    harvestapi only, no fallback actor (removed 2026-07-27 — see PRIMARY_ACTOR
    comment above). A 0-result query or an exception both just return empty;
    the caller's per-city/field loop already tolerates gaps.
    """
    query, url_input, scarce = args
    try:
        pin = _build_actor_input(PRIMARY_ACTOR, query, url_input, scarce=scarce)
        posts = _normalize_actor_items(PRIMARY_ACTOR, run_apify_actor(PRIMARY_ACTOR, pin))
        return query, posts
    except Exception as e:
        print(f"   [X] Primary scraper failed for query '{query[:60]}': {e}")
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

    # Quality-first: this is a SOFT ceiling on how many raw candidates we gather
    # per pass, not a quota to pad toward. We publish only what clears the gate.
    TARGET_VERIFIED = 60
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

    # ── Search queries — one plan per role track ───────────────────────────────
    # The query plan now lives in role_taxonomy.query_plan(). Before this, six
    # broad field buckets x 12 cities produced 78 queries in which "ai" was a
    # single word buried inside the data-science bucket and founder's-office /
    # forward-deployed / product-engineering / business-ops had no query at all
    # — which is exactly why the sheet held zero of those roles and 72%
    # marketing.
    #
    # The plan is deliberately WEIGHTED, not uniform: the scarce tracks get the
    # most query terms because they are what was missing, while marketing drops
    # from 13 queries to 5 because one query already returned 94 of 219 raw
    # posts. Abundant tracks rotate through the 12-city list by day-of-year, so
    # nationwide coverage happens across a week without paying for 12 cities
    # every night. ~118 queries total — comparable runtime to the old 78, since
    # Apify bills per RESULT and the narrow tracks return few.
    _rotation = datetime.now().timetuple().tm_yday
    query_specs = role_taxonomy.query_plan(rotation=_rotation)
    search_queries_count = len(query_specs)
    MAX_PER_QUERY = 12  # generous; location-targeted queries are already precise
    import random
    random.shuffle(query_specs)

    print("="*60)
    print(f"LINKEDIN POSTS SCRAPER - PARALLEL MODE")
    print(f"Target: {TARGET_VERIFIED} verified | Max per query: {MAX_PER_QUERY}")
    print(f"Plan: {search_queries_count} queries across {len(role_taxonomy.TRACKS)} "
          f"role tracks (city rotation {_rotation % len(role_taxonomy.ALL_CITIES)})")
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
    # ~118 queries run concurrently instead of sequentially. Apify calls are
    # pure I/O waits (1-3 min each) — threads eliminate that wait.
    query_inputs = []
    track_by_query = {}   # query -> its role track, so PHASE 2 knows the window
    for spec in query_specs:
        query = spec["query"]
        track_by_query[query] = spec["track"]
        search_url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?datePosted=%22past-24h%22&keywords={query.replace(' ', '%20')}"
            f"&origin=FACETED_SEARCH"
        )
        query_inputs.append((query, {"urls": [search_url], "limitPerSource": 40},
                             spec["scarce"]))

    # 8 workers, up from 5: the plan grew from 78 to ~118 queries and each is a
    # pure I/O wait on Apify, so the extra concurrency keeps wall-clock roughly
    # where it was rather than pushing the run past run_pipeline's timeout.
    _budget_ok, _budget_msg = check_apify_budget()
    print(f"\n[PHASE 1] {_budget_msg}")
    if not _budget_ok:
        print("   Aborting scrape — raise the Apify monthly cap or wait for the cycle to reset.")
        query_inputs = []
    print(f"[PHASE 1] Launching {len(query_inputs)} Apify scrapes in parallel ({APIFY_WORKERS} workers), "
          f"result budget {MAX_RESULTS_PER_RUN} "
          f"(~${MAX_RESULTS_PER_RUN * APIFY_USD_PER_RESULT:.2f}, "
          f"{_per_track_budget(len(role_taxonomy.TRACKS))}/track)...")
    all_raw_by_query = {}  # query -> list of raw posts
    with concurrent.futures.ThreadPoolExecutor(max_workers=APIFY_WORKERS) as executor:
        _track_budget = _per_track_budget(len(role_taxonomy.TRACKS))
        _spent = {t: 0 for t in role_taxonomy.TRACK_KEYS}
        _results_seen = [0]
        future_map = {executor.submit(_scrape_one_query, qi): qi[0] for qi in query_inputs}
        for future in concurrent.futures.as_completed(future_map):
            query_str = future_map[future]
            try:
                _, posts = future.result()
                # Result budget: once spent, drop further results on the floor
                # and cancel what hasn't started. Apify bills per result, so an
                # unbounded 118-query fan-out can burn a month's cap in one run.
                _tr = track_by_query.get(query_str, "")
                # Per-track budget: trim this query's haul to whatever share
                # its track has left. Results already fetched are already
                # billed, but trimming stops downstream LLM cost too and keeps
                # one track from dominating the raw pool.
                _left = max(0, _track_budget - _spent.get(_tr, 0))
                if _left <= 0:
                    all_raw_by_query[query_str] = []
                    continue
                posts = posts[:_left]
                _spent[_tr] = _spent.get(_tr, 0) + len(posts)
                _results_seen[0] += len(posts)
                all_raw_by_query[query_str] = posts
                print(f"   [ok] '{query_str[:60]}' -> {len(posts)} raw posts "
                      f"[{_tr} {_spent[_tr]}/{_track_budget}] "
                      f"(total {_results_seen[0]}/{MAX_RESULTS_PER_RUN})")
                if _results_seen[0] >= MAX_RESULTS_PER_RUN:
                    for f in future_map:
                        f.cancel()
            except Exception as e:
                print(f"   âŒ Query failed: {e}")
                all_raw_by_query[query_str] = []

    total_raw = sum(len(v) for v in all_raw_by_query.values())
    print(f"\n[PHASE 1 DONE] {total_raw} raw posts collected across all queries.")
    # Persist raw posts so the pre-filter funnel can be analyzed offline.
    try:
        with open(RAW_OUTPUT, "w", encoding="utf-8") as _rf:
            json.dump(all_raw_by_query, _rf, ensure_ascii=False)
    except Exception as _e:
        print(f"   (raw dump failed: {_e})")

    # â”€â”€ PHASE 2: Dedup + pre-filter (single-threaded, fast) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[PHASE 2] Deduplicating and pre-filtering...")
    all_to_llm = []
    for query_str, raw_posts in all_raw_by_query.items():
        if not raw_posts:
            continue
        _track = track_by_query.get(query_str, "")
        _max_days = 7 if role_taxonomy.is_scarce(_track) else 4
        passed = _pre_filter_posts(raw_posts, seen_urls, max_days=_max_days)
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
    # Location gating is delegated to quality_filter.location_decision (single
    # source of truth) — Bengaluru onsite/hybrid OR India-eligible remote only.

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

            # Bengaluru-onsite / India-remote gate (single source of truth).
            accept_loc, resolved_mode, loc_reason = quality_filter.location_decision(
                final_location, analysis.get("type") or "", post_text
            )
            if not accept_loc:
                print(f"    ❌ Skipped ({loc_reason}): {final_company}")
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
                # Genuineness score from quality_filter.evaluate_post, carried
                # through llm_post_analyzer. role_taxonomy.balance ranks by it
                # so a capped track keeps its BEST posts, not an arbitrary slice.
                "quality_score": post.get("quality_score", 0),
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

    # ── PHASE 5: Role balance ────────────────────────────────
    # Runs AFTER the quality gate and AFTER the topup merge, never before.
    # quality_filter decides what is PUBLISHABLE; this only decides which of
    # the survivors to publish, capping each role track so one oversupplied
    # field can't take the whole night (marketing was 72% of the live sheet).
    # It never pads — short supply just yields fewer, preserving the
    # quality-first contract in run_pipeline.py. Running it after the merge
    # matters: otherwise a topup pass re-floods the track the first pass
    # just capped.
    _pre_balance = len(verified_posts)
    _mix_before = role_taxonomy.mix(verified_posts)
    verified_posts = role_taxonomy.balance(verified_posts)
    print(f"\n[PHASE 5] Role balance: {_pre_balance} → {len(verified_posts)} posts")
    print(f"   before: {_mix_before}")
    print(f"   after : {role_taxonomy.mix(verified_posts)}")

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
