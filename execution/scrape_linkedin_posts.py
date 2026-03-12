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
    NO filtering — all posts pass through.
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
            headline_lower = author_headline.lower()
            # Try "at Company" pattern
            at_match = re.search(r'\bat\s+([A-Z][\w\s&\.]+?)(?:\s*[|·•\-–]|$)', author_headline)
            if at_match:
                author_company = at_match.group(1).strip()
            else:
                # Try "Role | Company" or "Role - Company" pattern
                sep_match = re.search(r'[|·•\-–]\s*([A-Z][\w\s&\.]+?)(?:\s*[|·•\-–]|$)', author_headline)
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
        
        # Safe int conversion
        def safe_int(val):
            if isinstance(val, list): return len(val)
            if isinstance(val, dict): return val.get("count", 0) or 0
            try: return int(val) if val else 0
            except (ValueError, TypeError): return 0
        
        likes = safe_int(likes)
        comments = safe_int(comments)
        reposts = safe_int(reposts)
        
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
        is_stale = True if (hours_old is not None and hours_old > 12 and engagement_score == 0) else False
        
        # Build clean record — ALL posts pass through
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
        print(f"   ⚠️ Actor {actor_id} run {run.get('id')} ended with status: {status}")
        # Even if failed, some items might have been saved to the dataset
        # But for reliability, we should treat it as a failure if we got 0 items
    
    # Fetch results from dataset
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Actor returned {len(items)} items")
    
    if not items and status != "SUCCEEDED":
        raise Exception(f"Apify actor {actor_id} failed with status {status}")
        
    return items


def main():
    """
    Main execution flow (Iterative Mode):
    1. Pick keyword
    2. Scrape
    3. LLM Verify
    4. Check if target reached (30)
    5. Repeat
    """
    ensure_tmp_dir()
    
    TARGET_VERIFIED = 130  # Aim for 130 posts
    verified_posts = []
    seen_urls = set()
    
    # Top 20 high-value internship keywords
    # Optimized Boolean Queries (Grouped for speed, respecting LinkedIn limits)
    search_queries = [
        # Group 1: High Intent (India-specific)
        "(hiring intern india) OR (internship opportunity) OR (paid internship india) OR (we are hiring intern)",
        
        # Group 2: Tech & Engineering
        "(sde intern) OR (software intern) OR (full stack intern) OR (data science intern) OR (ml intern)",
        
        # Group 3: Business & Product
        "(product intern) OR (marketing intern) OR (business development intern) OR (founder's office intern)",
        
        # Group 4: Design, Content & Finance (India-specific)
        "(ui ux intern) OR (content intern) OR (finance intern) OR (hr intern india)",
        
        # Group 5: Analytics & Growth
        "(data analyst intern) OR (growth intern) OR (sales intern) OR (internship alert)",
        
        # Group 6: Startup & Misc
        "(startup internship) OR (looking for interns) OR (hiring interns remote) OR (apply now internship)"
    ]
    
    print("="*60)
    print(f"LINKEDIN POSTS SCRAPER - ITERATIVE MODE")
    print(f"Target: {TARGET_VERIFIED} Verified Leads")
    print("="*60)
    
    # Check LLM availability
    # Configure LLM dynamically
    try:
        import llm_post_analyzer
    except ModuleNotFoundError:
        import execution.llm_post_analyzer as llm_post_analyzer
    llm_post_analyzer.configure_llm()
    print(f"✅ LLM Verification Enabled ({llm_post_analyzer.PROVIDER.title()})")
    
    # Use module function
    filter_posts_with_llm = llm_post_analyzer.filter_posts_with_llm
    
    use_llm = True if llm_post_analyzer.PROVIDER != "none" else False
    
    for i, query in enumerate(search_queries):
        if len(verified_posts) >= TARGET_VERIFIED:
            print(f"\n🎉 Target reached! ({len(verified_posts)} verified posts)")
            break
            
        print(f"\n[{i+1}/{len(search_queries)}] Scraping: '{query}'...")
        print(f"   Current Verified Count: {len(verified_posts)}/{TARGET_VERIFIED}")
        
        # Scrape
        search_url = f"https://www.linkedin.com/search/results/content/?datePosted=%22past-24h%22&keywords={query.replace(' ', '%20')}&origin=FACETED_SEARCH"
        run_input = {"urls": [search_url], "limitPerSource": 50} # Fetch 50 per keyword
        
        raw_posts = []
        try:
            raw_posts = run_apify_actor(PRIMARY_ACTOR, run_input)
        except Exception as e:
            print(f"   ❌ Primary Scraper Failed: {e}")
            print(f"   🔄 Retrying with Fallback Scraper: {FALLBACK_ACTOR}...")
            try:
                # Adjust input for fallback actor if needed (usually similar for scraping actors)
                raw_posts = run_apify_actor(FALLBACK_ACTOR, run_input)
            except Exception as e2:
                print(f"   ❌ Fallback Scraper also failed: {e2}")
                continue
            
        if not raw_posts:
            print("   ⚠️ No posts found for this keyword")
            continue
            
        # Dedup immediately — by URL AND by normalized text content
        new_unique = []
        for p in raw_posts:
            url = p.get("url") or p.get("post_url") or p.get("postUrl") or p.get("link")
            raw_text = (p.get("text") or p.get("postText") or p.get("content") or "")
            
            # Normalize text for dedup: strip emojis/special chars, lowercase, collapse whitespace
            norm_text = re.sub(r'[^\w\s]', '', raw_text[:300]).lower()
            norm_text = re.sub(r'\s+', ' ', norm_text).strip()[:150]
            text_hash = hash(norm_text) if norm_text else None
            
            # Block known spam patterns (generic role lists with no company)
            if norm_text and "hiring for multiple positions" in norm_text:
                continue
            if norm_text and "apply now for internship" in norm_text and "hiring" in norm_text:
                continue
                
            # Block posts about "my journey", "vibecoding", "I got a job" (personal stories)
            story_keywords = ["my journey", "wrapped up my time", "excited to announce", "officially a", "vibecoding", "employee market hai", "from learning to earning", "i am looking for", "i'm looking for", "seeking a", "seeking an", "open to work"]
            is_story = any(kw in norm_text for kw in story_keywords)
            if is_story:
                continue
                
            # Must have some hiring intent if it's not explicitly blocked
            hiring_keywords = ["hiring", "looking for", "apply", "opportunity", "openings", "interns required", "join our team", "we are expanding", "internship alert"]
            has_hiring_intent = any(kw in norm_text for kw in hiring_keywords)
            if not has_hiring_intent and not "intern" in norm_text:
                continue
            
            # Skip if we've seen this normalized text before
            if text_hash and text_hash in seen_urls:
                continue
            
            if url and url not in seen_urls:
                seen_urls.add(url)
                if text_hash:
                    seen_urls.add(text_hash)
                new_unique.append(p)
            elif not url and text_hash:
                seen_urls.add(text_hash)
                new_unique.append(p)
        
        print(f"   Found {len(new_unique)} unique new posts")
        if not new_unique:
            continue
            
        # Add strict explicit time filtering before LLM check
        time_filtered = []
        for p in new_unique:
            posted_time = str(p.get("postedTime") or p.get("publishedAt") or p.get("time") or "").lower().strip()
            
            # If the timestamp contains week, month, or year, it's strictly > 4 days old
            if "w" in posted_time or "mo" in posted_time or "yr" in posted_time or "year" in posted_time or "month" in posted_time or "week" in posted_time:
                continue
                
            # If the timestamp contains days and is > 4, it's too old
            days_match = re.search(r"(\d+)\s*d", posted_time)
            if days_match and int(days_match.group(1)) > 4:
                continue
                
            time_filtered.append(p)
            
        print(f"   Excluded {len(new_unique) - len(time_filtered)} posts older than 4 days before LLM check")
        new_unique = time_filtered
        
        if not new_unique:
            continue
            
        # HYBRID: LLM for extraction (company, role, location) + Regex for email/apply link
        batch_verified = []
        if use_llm:
            print("   🤖 Running LLM Extraction (no filtering)...")
            llm_results = filter_posts_with_llm(new_unique)
            
            for post in llm_results:
                analysis = post.get("llm_analysis", {})
                if isinstance(analysis, list):
                    analysis = analysis[0] if analysis else {}
                
                # LLM extraction: ALL fields
                llm_company = analysis.get("company") or ""
                llm_roles = analysis.get("roles", [])
                llm_location = analysis.get("location") or ""
                llm_email = analysis.get("contact_email") or ""
                llm_apply_link = analysis.get("apply_link") or ""
                llm_work_type = analysis.get("work_type") or ""
                
                # Apify author data as fallback for company
                author_name = post.get("authorName") or post.get("author", {}).get("name", "") or ""
                author_headline = post.get("authorHeadline") or post.get("author", {}).get("headline", "") or ""
                
                # Company: LLM > Apify author.company > headline parse > author name
                final_company = llm_company if llm_company not in [None, "", "null", "Unknown"] else ""
                if not final_company:
                    final_company = post.get("authorCompany") or post.get("author", {}).get("company", "") or ""
                if not final_company:
                    at_match = re.search(r'\bat\s+([A-Z][\w\s&\.]+?)(?:\s*[|·•\-–]|$)', author_headline)
                    if at_match:
                        final_company = at_match.group(1).strip()
                if not final_company:
                    final_company = author_name
                
                # Role: LLM extracted
                final_role = llm_roles[0] if llm_roles and llm_roles[0] not in [None, ""] else "Internship"
                
                # Location: LLM extracted
                final_location = llm_location if llm_location not in [None, "", "null", "Unknown"] else ""
                
                post_text = post.get("text") or post.get("postText") or post.get("content") or ""
                url = post.get("url") or post.get("postUrl") or post.get("link") or ""
                
                # --- INDIA-ONLY LOCATION FILTER ---
                # Whitelist approach: only keep India / Remote / Indian cities
                india_keywords = [
                    "india", "remote", "work from home", "wfh",
                    "bangalore", "bengaluru", "mumbai", "delhi", "new delhi",
                    "gurgaon", "gurugram", "noida", "hyderabad", "chennai",
                    "pune", "kolkata", "ahmedabad", "jaipur", "lucknow",
                    "chandigarh", "indore", "kochi", "coimbatore", "nagpur",
                    "bhopal", "visakhapatnam", "thiruvananthapuram", "surat",
                    "vadodara", "mysore", "mangalore", "pan india",
                ]
                loc_lower = final_location.lower()
                text_lower = post_text.lower()
                is_india = any(kw in loc_lower or kw in text_lower for kw in india_keywords)
                if not is_india:
                    print(f"    ❌ Skipped (not India): {final_location or 'Unknown location'}")
                    continue
                
                clean_post = {
                    "author_name": author_name,
                    "author_headline": author_headline,
                    "post_text": post_text[:500],
                    "posted_time": post.get("postedTime") or post.get("postedAtISO") or "",
                    "likes": post.get("likes") or 0,
                    "comments": post.get("comments") or 0,
                    "url": url,
                    
                    # Exact 1-to-1 Schema
                    "title": final_role,
                    "type": analysis.get("type") or "",
                    "timing": analysis.get("timing") or "",
                    "description": post_text[:5000],  # Give more text
                    "stipend": analysis.get("stipend") or "",
                    "duration": analysis.get("duration") or "",
                    "experience": analysis.get("experience") or "",
                    "location": final_location,
                    "deadline": analysis.get("deadline") or "",
                    "tags": analysis.get("tags") or [],
                    "hiringOrganization": final_company,
                    "contact_email": llm_email,
                    "apply_link": llm_apply_link,
                    
                    # Legacy internal fields
                    "role": final_role,       # Needed by aggregate
                    "company": final_company, # Needed by aggregate
                    "work_type": llm_work_type, # Needed by aggregate
                    "hiring_signals": ["llm_extracted"],
                    "engagement_score": 1,
                    "freshness_bonus": 1,
                    "is_stale": False,
                }
                batch_verified.append(clean_post)
        else:
            # Pure regex fallback (no LLM available)
            batch_verified = filter_posts(new_unique)
            
        print(f"   ✅ Verified {len(batch_verified)} leads from this batch")
        verified_posts.extend(batch_verified)
        
    # Final Fallback check
    if len(verified_posts) < 10:
        print("\n⚠️ Warning: Very few verified posts found. Relaxing filters might be needed.")

    # Save output
    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(verified_posts, f, indent=2, ensure_ascii=False)
    print(f"\nsaved clean output: {CLEAN_OUTPUT} ({len(verified_posts)} posts)")
    
    return verified_posts



if __name__ == "__main__":
    results = main()
    print(f"\nTotal filtered posts: {len(results)}")
    
    # Show top 3 for verification
    if results:
        print("\nTop 3 posts:")
        for i, post in enumerate(results[:3], 1):
            print(f"  {i}. {post['author_name']} - Signals: {post['hiring_signals']}")
