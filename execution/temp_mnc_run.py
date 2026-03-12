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
RAW_OUTPUT = os.path.join(TMP_DIR, "mnc_run_raw.json")
CLEAN_OUTPUT = os.path.join(TMP_DIR, "mnc_run_clean.json")

# Filter thresholds
MAX_HOURS_OLD = 96  # Strict 4 days limit (user requested)
PREFERRED_HOURS = 24  # Soft preference
MIN_HIRING_SIGNALS = 1  # Relaxed to 1 signal

# Apify actors (user-specified with correct schema)
PRIMARY_ACTOR = "supreme_coder/linkedin-post"  # User-specified
FALLBACK_ACTOR = "apimaestro/linkedin-posts-search-scraper-no-cookies"  # Backup

# Hiring intent keywords
ROLE_KEYWORDS = ["hiring", "looking for", "opening", "position", "opportunity", "vacancy", "recruit"]
ROLE_TYPES = ["intern", "internship", "job", "fresher", "trainee", "associate", "entry level", "apprentice", "apprenticeship"]
ACTION_WORDS = ["apply", "dm", "send resume", "share cv", "drop your resume", "send your cv", "reach out", "contact"]
URGENCY_WORDS = ["immediate", "urgent", "asap", "starting soon", "immediate joining", "walk-in"]
CONTACT_PATTERNS = [r"[\w\.-]+@[\w\.-]+", r"forms\.gle", r"bit\.ly", r"linkedin\.com/in/", r"comment below"]


def ensure_tmp_dir():
    """Ensure .tmp directory exists."""
    os.makedirs(TMP_DIR, exist_ok=True)


def parse_posted_time(posted_str: str, timestamp: int = None) -> int | None:
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


def filter_posts(posts: list) -> list:
    """
    Apply hiring-intent and freshness filters.
    Returns list of clean, schema-compliant records.
    """
    clean_posts = []
    
    for post in posts:
        # Extract fields with fallbacks
        author_name = post.get("authorName") or post.get("author", {}).get("name") or ""
        author_headline = post.get("authorHeadline") or post.get("author", {}).get("headline") or ""
        post_text = post.get("text") or post.get("postText") or post.get("content") or ""
        posted_time = post.get("postedTime") or post.get("publishedAt") or post.get("time") or ""
        likes = post.get("likes") or post.get("likeCount") or post.get("numLikes") or 0
        comments = post.get("comments") or post.get("commentCount") or post.get("numComments") or 0
        reposts = post.get("reposts") or post.get("repostCount") or 0
        url = post.get("url") or post.get("postUrl") or post.get("link") or ""
        
        # Ensure numeric types (handle list/dict types from API)
        def safe_int(val):
            if isinstance(val, list):
                return len(val)
            if isinstance(val, dict):
                return val.get("count", 0) or 0
            try:
                return int(val) if val else 0
            except (ValueError, TypeError):
                return 0
        
        likes = safe_int(likes)
        comments = safe_int(comments)
        reposts = safe_int(reposts)
        
        # Extract timestamp (priority for accurate age calculation)
        timestamp = post.get("postedAtTimestamp") or post.get("timestamp")
        iso_date = post.get("postedAtISO") or post.get("publishedAt") or posted_time
        
        # Filter: Freshness check (use timestamp if available, else ISO/relative)
        hours_old = parse_posted_time(iso_date, timestamp)
        
        # STRICT: Skip posts older than 4 days (96 hours)
        if hours_old is not None and hours_old > MAX_HOURS_OLD:
            print(f"  SKIP (old): {hours_old}h - {post_text[:50]}...")
            continue
        
        # STRICT: Also skip if no date info (unknown age)
        if hours_old is None:
            # Try to detect if it's likely an old post based on text patterns
            text_lower = post_text.lower()
            if any(old_indicator in text_lower for old_indicator in ["last year", "months ago", "2025", "2024"]):
                print(f"  SKIP (likely old): no timestamp, suspicious text")
                continue
        
        # Filter: Hiring intent (must match 2+ signals)
        hiring_signals = detect_hiring_signals(post_text)
        if len(hiring_signals) < MIN_HIRING_SIGNALS:
            continue
        
        # Calculate engagement score
        engagement_score = calculate_engagement_score(likes, comments, reposts)
        
        # Flag: Low engagement on older posts (deprioritize but don't exclude)
        is_stale = False
        if hours_old is not None and hours_old > 12 and engagement_score == 0:
            is_stale = True
        
        # Freshness preference scoring
        freshness_bonus = 0
        if hours_old is not None and hours_old <= PREFERRED_HOURS:
            freshness_bonus = 1
        
        # Extract role from post text
        role = extract_role(post_text)
        
        # Build clean record
        clean_posts.append({
            "author_name": author_name,
            "author_headline": author_headline,
            "post_text": post_text[:500] + "..." if len(post_text) > 500 else post_text,
            "posted_time": posted_time,
            "likes": likes,
            "comments": comments,
            "url": url,
            "role": role,
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
    
    # Fetch results from dataset
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Actor returned {len(items)} items")
    
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
    
    TARGET_VERIFIED = 120  # Target 120 verified internships
    verified_posts = []
    seen_urls = set()
    
    # Top 20 high-value internship keywords
    # Optimized Boolean Queries (Grouped for speed, respecting LinkedIn limits)
    # MNC & Apprenticeship Focussed Queries
    search_queries = [
        # General & Startup Queries (Broader scope)
        "finance intern hiring india",
        "marketing intern hiring india",
        "operations intern hiring india",
        "startup intern hiring india",
        "business analyst intern hiring india",
        "human resources intern hiring india",
        "product management intern hiring india",
        "software engineering intern hiring india",
        "data science intern hiring india",
        "summer intern hiring india",
    ]
    
    print("="*60)
    print(f"LINKEDIN POSTS SCRAPER - ITERATIVE MODE")
    print(f"Target: {TARGET_VERIFIED} Verified Leads")
    print("="*60)
    
    # Check LLM availability
    # Configure LLM dynamically
    import llm_post_analyzer
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
        
        # Revert to URL based input (proven to run)
        # Revert to URL based input (proven to run)
        # Revert to quoted datePosted (works)
        search_url = f"https://www.linkedin.com/search/results/content/?datePosted=%22past-week%22&keywords={query.replace(' ', '%20')}&origin=FACETED_SEARCH"
        run_input = {"urls": [search_url], "limitPerSource": 50} 
        
        raw_posts = []
        try:
            raw_posts = run_apify_actor(PRIMARY_ACTOR, run_input)
            
            # Save RAW output for debugging
            if raw_posts:
                with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
                    json.dump(raw_posts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   ❌ Scrape failed: {e}")
            continue
            
        if not raw_posts:
            print("   ⚠️ No posts found for this keyword")
            continue
            
        # Dedup immediately
        new_unique = []
        for p in raw_posts:
            url = p.get("url") or p.get("post_url") or p.get("postUrl") or p.get("link")
            if url and url not in seen_urls:
                seen_urls.add(url)
                new_unique.append(p)
            elif not url:
                # Dedupe by text hash if no URL
                text_hash = hash((p.get("text") or "")[:100])
                if text_hash not in seen_urls:
                    seen_urls.add(text_hash)
                    new_unique.append(p)
        
        print(f"   Found {len(new_unique)} unique new posts")
        if not new_unique:
            continue
            
        # Filter / Verify
        batch_verified = []
        if use_llm:
            # OPTIMIZATION: Pre-filter junk/old posts locally to save LLM calls
            pre_filtered = []
            print(f"   Pre-filtering {len(new_unique)} posts...")
            for p in new_unique:
                # Author Type Detection
                author = p.get("author", {})
                urn = author.get("entityUrn", "")
                if "miniCompany" in urn or "company" in urn:
                    p["author_type"] = "Company"
                else:
                    p["author_type"] = "Individual"

                # 1. Repost detection - skip reposts
                is_repost = (
                    p.get("isRepost") or 
                    p.get("repostedBy") or 
                    p.get("reshared") or
                    p.get("isReshare") or
                    p.get("type", "").lower() in ["repost", "reshare"]
                )
                if is_repost:
                    continue
                
                # Also check text for repost indicators
                text_raw = p.get("text") or p.get("post_text") or ""
                text_lower_check = text_raw.strip().lower()
                if text_lower_check.startswith("repost") or text_lower_check.startswith("re-post") or text_lower_check.startswith("resharing") or text_lower_check.startswith("sharing this"):
                    continue

                # 2. Freshness check (use local parse_posted_time)
                iso_date = p.get("postedAtISO") or p.get("postedTime")
                timestamp = p.get("postedAtTimestamp")
                hours_old = parse_posted_time(iso_date, timestamp)
                
                if hours_old is not None and hours_old > 96: # 4 days
                    continue
                    
                pre_filtered.append(p)

            print(f"   Pre-filtering kept {len(pre_filtered)}/{len(new_unique)} posts")

            # 3. LLM/Regex Verification
            batch_verified = []
            try:
                if len(pre_filtered) > 0:
                    print(f"   🤖 Running Verification on {len(pre_filtered)} relevant posts...")
                    # This will use the configured provider (Regex/OpenAI/Gemini)
                    llm_results = filter_posts_with_llm(pre_filtered)
                
                for post in llm_results:
                    analysis = post.get("llm_analysis", {})
                    if analysis.get("should_include", False):
                        # Get LLM extracted values
                        llm_role = analysis.get("role")
                        llm_company = analysis.get("company")
                        llm_location = analysis.get("location")
                        
                        # Get author name from Apify data
                        author_name = post.get("authorName") or post.get("author", {}).get("name", "") or "Unknown Author"
                        
                        # Use LLM values if available
                        final_role = llm_role if llm_role and llm_role not in ["Internship", "General Intern", None, ""] else "Internship"
                        final_company = llm_company if llm_company not in [None, "", "null"] else author_name
                        final_location = llm_location if llm_location not in [None, "", "null"] else "Not specified"
                        
                        # Handle Work Type
                        work_type = analysis.get("work_type", "")
                        
                        clean_post = {
                            "author_name": author_name,
                            "author_headline": post.get("authorHeadline") or post.get("author", {}).get("headline", ""),
                            "post_text": (post.get("text") or post.get("post_text") or "")[:500],
                            "posted_time": post.get("postedTime") or post.get("postedAtISO") or "",
                            "likes": post.get("likes") or 0,
                            "comments": post.get("comments") or 0,
                            "url": post.get("url") or post.get("postUrl") or post.get("link") or post.get("post_url") or "",
                            "role": final_role,
                            "company": final_company,
                            "location": final_location,
                            "work_type": work_type,
                            "hiring_signals": ["llm_verified"],
                            "engagement_score": 1,
                            "freshness_bonus": 1,
                            "is_stale": False,
                            "llm_confidence": analysis.get("confidence", 0.5),
                            "apply_link": analysis.get("apply_link", "")
                        }
                        batch_verified.append(clean_post)
            except Exception as e:
                print(f"   ❌ Verification failed for this batch: {e}")
                # Optional: debug traceback
                # import traceback; traceback.print_exc()

            print(f"   ✅ Verified {len(batch_verified)} leads from this batch")
            verified_posts.extend(batch_verified)
            
            # Save intermediate progress
            with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
                json.dump(verified_posts, f, indent=2, ensure_ascii=False)
            print(f"   💾 Progress saved: {len(verified_posts)} total")
            

        
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
    
    # Auto-publish to Google Sheets
    if results:
        print("\n🚀 Publishing to Google Sheets...")
        try:
            import subprocess
            subprocess.run(["python", "execution/publish_mnc_run.py"], check=True)
        except Exception as e:
            print(f"❌ Publishing failed: {e}")
    
    # Show top 3 for verification
    if results:
        print("\nTop 3 posts:")
        for i, post in enumerate(results[:3], 1):
            print(f"  {i}. {post['author_name']} - Signals: {post['hiring_signals']}")
