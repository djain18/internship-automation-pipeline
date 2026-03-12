"""
llm_post_analyzer.py
--------------------
Uses OpenAI (GPT-4o-mini) or Groq (Llama 3.1 70B) to analyze LinkedIn posts.
Prioritizes OpenAI if OPENAI_API_KEY is present.
"""

import os
import json
import re as _re_module
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENAI_AVAILABLE = False
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    pass

GROQ_AVAILABLE = False
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    pass

# Gemini conditionally
GEMINI_AVAILABLE = False

# Defauts
PROVIDER = "none"
CLIENT = None
MODEL = "none"
REQUEST_DELAY = 1.0 

def analyze_post_regex(post_text: str, posted_time_str: str = None) -> dict:
    """Analyze post using Regex (Fallback for when LLMs are down)."""
    import re
    
    text_lower = post_text.lower()
    
    # 1. Freshness (Simple parsing)
    is_fresh = True
    age_days = 0
    if posted_time_str:
        if "mo" in posted_time_str or "yr" in posted_time_str:
            is_fresh = False
            age_days = 30
        elif "w" in posted_time_str:
            # "1w" -> 7 days
            try:
                weeks = int(re.search(r'(\d+)w', posted_time_str).group(1))
                age_days = weeks * 7
                if age_days > 8: is_fresh = False
            except: pass
        elif "d" in posted_time_str:
            try:
                days = int(re.search(r'(\d+)d', posted_time_str).group(1))
                age_days = days
                if days > 8: is_fresh = False
            except: pass
            
    # 2. Roles
    roles = []
    # Look for "hiring for X", "looking for X"
    role_matches = re.findall(r'(?:hiring|looking) for ([\w\s]+?)(?:intern|internship)', text_lower)
    if role_matches:
        roles = [r.strip().title() + " Intern" for r in role_matches[:2]]
    
    if not roles:
        # Fallback keyword search
        keywords = ["marketing", "finance", "sales", "hr", "operations", "tech", "data", "software", "business development", "product", "design", "graphic", "content"]
        for kw in keywords:
            if kw in text_lower and "intern" in text_lower:
                roles.append(kw.title() + " Intern")
                
    if not roles:
        roles = ["Internship"]
        
    # 3. Company
    company = ""
    # Look for "at [Company]" - avoid common stopwords
    at_match = re.search(r'\bat ([A-Z][\w\s\.]+?)(?:\.|,|\n| is| hiring| looking|!)', post_text)
    if at_match and len(at_match.group(1)) < 30:
        cand = at_match.group(1).strip()
        if cand.lower() not in ["the", "a", "an", "this", "my", "our", "least", "target", "all"]:
            company = cand
            
    # Clean up if it looks like a URL
    if "." in company and not " " in company:
         company = re.sub(r'https?://|www\.|', '', company).split('/')[0]
        
    # 4. Location
    location = ""
    cities = ["bangalore", "bengaluru", "mumbai", "delhi", "gurgaon", "noida", "hyderabad", "chennai", "pune", "kolkata", "ahmedabad", "remote", "work from home"]
    found_locs = []
    for city in cities:
        if city in text_lower:
            found_locs.append(city.title())
    
    if "remote" in text_lower or "work from home" in text_lower:
        location = "Remote"
    elif found_locs:
        location = found_locs[0]
        
    # 5. Apply Link
    apply_link = ""
    url_match = re.search(r'(https?://[^\s]+)', post_text)
    if url_match:
        apply_link = url_match.group(1)
        
    # 6. Work Type
    work_type = ""
    if "part-time" in text_lower or "part time" in text_lower:
        work_type = "Part-time"
    elif "full-time" in text_lower or "full time" in text_lower:
        work_type = "Full-time"
        
    # 7. Spam Check
    should_include = True
    exclude_reason = ""
    
    if "registration fee" in text_lower or "security deposit" in text_lower:
        should_include = False
        exclude_reason = "Spam keywords detected"
    elif not is_fresh:
        should_include = False
        exclude_reason = "Old post (> 4 days)"
    elif not company and not "hiring" in text_lower:
        # If no company name found AND "hiring" not explicitly clean, be careful
        # But for regex, we might just pass it and let user filter
        pass
        
    return {
        "is_fresh": is_fresh,
        "age_days_estimate": age_days,
        "age_explanation": "Regex parsed",
        "roles": roles, # Array
        "company": company,
        "location": location,
        "apply_link": apply_link,
        "work_type": work_type,
        "is_hiring_post": True,
        "should_include": should_include,
        "exclude_reason": exclude_reason
    }

def configure_llm():
    """Configure the LLM client (OpenRouter > OpenAI > Gemini > Groq)."""
    global PROVIDER, CLIENT, MODEL, REQUEST_DELAY
    
    # 0. Try OpenRouter (gpt-oss-120b)
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and OPENAI_AVAILABLE:
        print("✅ Using OpenRouter (gpt-oss-120b) - EXTRACTION ONLY")
        PROVIDER = "openai"
        CLIENT = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
        )
        MODEL = "openai/gpt-oss-120b"
        REQUEST_DELAY = 1.0
        return

    # 1. Try Gemini (Primary - User Requested)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and GEMINI_AVAILABLE:
        print("✅ Using Gemini (gemini-2.5-flash-lite) - EXTRACTION ONLY")
        genai.configure(api_key=gemini_key)
        PROVIDER = "gemini"
        CLIENT = genai.GenerativeModel("gemini-2.5-flash-lite")
        MODEL = "gemini-2.5-flash-lite"
        REQUEST_DELAY = 1.0
        return
        
    # 2. Try OpenAI (Fallback)
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and OPENAI_AVAILABLE:
        # OpenAI disabled as primary
        pass
    
    # 3. Try Groq
    # groq_key = os.getenv("GROQ_API_KEY")
    # if groq_key and GROQ_AVAILABLE:
    #     print("⚠️ Using Groq (Llama 3.1) - Rate limits apply")
    #     PROVIDER = "groq"
    #     CLIENT = Groq(api_key=groq_key)
    #     MODEL = "llama-3.1-8b-instant"
    #     REQUEST_DELAY = 5.0 
    #     return
        
    # 4. Fallback to Regex (Always available)
    print("⚠️ Using Regex Analysis (Raw Code) - No AI, extracting patterns...")
    PROVIDER = "regex"
    REQUEST_DELAY = 0.0
    return

def analyze_post(client, post_text: str, posted_time_str: str = None, current_date: str = None) -> dict:
    """Analyze post using configured LLM."""
    if not current_date:
        current_date = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""Extract structured data from this LinkedIn post.

TEXT: {post_text[:3000]}

EXTRACT the following fields from the post. Be accurate — only extract what is explicitly stated.

1. COMPANY: The company or organization that is hiring.
   - Look for company names mentioned in the post text.
   - If the post says "at [Company]" or "[Company] is hiring", extract that name.
   - Remove domain extensions (.com, .in, .io) from company names.
   - If truly no company is mentioned anywhere, output "Unknown".

2. ROLES: List ALL specific internship/job role names mentioned.
   - If multiple roles (e.g. "Marketing & Sales Intern"), split into array: ["Marketing Intern", "Sales Intern"]
   - If only generic "intern" or "internship" is mentioned, output ["Internship"]

3. LOCATION: City, state, or "Remote" / "Work From Home".
   - Extract the specific city/state if mentioned.
   - If "remote" or "work from home" or "WFH", output "Remote".
   - If multiple cities mentioned, list up to 2 separated by comma.
   - If no location is mentioned at all, output "Unknown".

4. TYPE: Output exactly one of: "Remote", "Hybrid", "Onsite", or null.
   - Parse from the text context if explicitly stated.

5. TIMING: Output exactly one of: "Full-time", "Part-time", or null.

6. STIPEND: Extract stipend/salary details (e.g. "10k/month", "paid", "₹15,000/month"). Output null if missing.
   - CRITICAL: Do NOT confuse years (2024, 2025, 2026, 2027) with stipend amounts. Years are NOT stipends.
   - Only extract actual monetary amounts or keywords like "paid", "unpaid".
   - If no explicit stipend/salary is mentioned, output null.

7. DURATION: Extract internship duration (e.g. "3 months", "6 months"). Output null if missing.

8. EXPERIENCE: Extract required experience (e.g. "Fresher", "1-2 years", "2024 graduate"). Output null if missing.

9. DEADLINE: Extract the application deadline date or time if present. Output null if missing.
   - If a specific date is mentioned, output it in YYYY-MM-DD format if possible.

10. TAGS: Output an array of up to 3 relevant categorical tags (e.g. ["Engineering", "Python", "Startup"]).

11. CONTACT_EMAIL: Extract any email address mentioned in the post. Empty string if none.

12. APPLY_LINK: Extract any URL/link mentioned for applying. Empty string if none.

IMPORTANT: This is EXTRACTION ONLY. Always set should_include to true.

Output JSON:
{{
    "company": "string",
    "roles": ["string"],
    "location": "string",
    "type": "Remote | Hybrid | Onsite | null",
    "timing": "Full-time | Part-time | null",
    "stipend": "string or null",
    "duration": "string or null",
    "experience": "string or null",
    "deadline": "string or null",
    "tags": ["string"],
    "contact_email": "string or empty",
    "apply_link": "string or empty",
    "should_include": true
}}
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            content = ""
            
            if PROVIDER == "gemini":
                # Gemini Call
                response = client.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                content = response.text
                
            elif PROVIDER == "regex":
                 pass
                
            elif PROVIDER == "openai":
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                
            elif PROVIDER == "groq":
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content

            # Clean markdown
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
                
            try:
                data = json.loads(content)
                return data
            except:
                if isinstance(content, dict): return content
                return {}
            
        except Exception as e:
            error_str = str(e)
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"LLM Error ({PROVIDER}): {e}")
                return {"should_include": False, "exclude_reason": f"Error: {e}"}

def _try_fallback_provider():
    pass

def batch_analyze_posts(posts: list) -> list:
    """Analyze a batch of posts — EXTRACTION ONLY, no filtering."""
    if not CLIENT:
        configure_llm()
    
    if not CLIENT:
        return []
        
    analyzed = []
    print(f"Analyzing {len(posts)} posts with {PROVIDER} ({MODEL})...")
    
    import re as _re
    
    for i, post in enumerate(posts):
        text = post.get("text", "")
        if not text: continue
        
        print(f"  [{i+1}/{len(posts)}] Analyzing: {text[:50]}...")
        if PROVIDER == "regex":
             analysis = analyze_post_regex(text, post.get("posted_time"))
        else:
             analysis = analyze_post(CLIENT, text, post.get("posted_time"))
        
        post["llm_analysis"] = analysis
        
        # Ensure analysis is a dict
        if isinstance(analysis, list):
            analysis = analysis[0] if analysis else {}
            
        # Check if the post should be filtered out
        if not analysis.get("should_include", True):
            reason = analysis.get("exclude_reason", "LLM judged irrelevant (e.g., outside India)")
            print(f"    ❌ Skipped: {reason}")
            continue
        
        # EXTRACTION ONLY — ALL posts pass through, no filtering
        company = analysis.get("company", "") or ""
        company = company.strip()
        
        # Clean company name (remove URLs/domains)
        if ".com" in company.lower() or "www." in company.lower() or "http" in company.lower():
            try: 
                clean_name = _re.sub(r'https?://|www\.', '', company).split('/')[0]
                clean_name = clean_name.replace('.com', '').replace('.in', '').replace('.co', '')
                company = clean_name.title()
            except: pass
        
        location = analysis.get("location", "") or ""
        type_str = analysis.get("type", "") or ""
        timing = analysis.get("timing", "") or ""
        stipend = analysis.get("stipend", "") or ""
        duration = analysis.get("duration", "") or ""
        experience = analysis.get("experience", "") or ""
        deadline = analysis.get("deadline", "") or ""
        tags = analysis.get("tags", [])
        
        contact_email = analysis.get("contact_email", "") or ""
        apply_link = analysis.get("apply_link", "") or ""
        work_type = analysis.get("work_type", "") or "" # Legacy fallback
        
        if not timing and work_type:
            timing = work_type
        
        # --- FIX 1: STIPEND YEAR SANITIZER ---
        # Strip 4-digit years (2020-2030) that the LLM mistakes for stipend
        if stipend:
            stipend_clean = stipend.strip()
            # If stipend is purely a 4-digit year, null it out
            if _re.fullmatch(r'\d{4}', stipend_clean) and 2020 <= int(stipend_clean) <= 2030:
                stipend = ""
            # If stipend contains a year as the only number, null it out  
            elif _re.fullmatch(r'(20[2-3]\d)', stipend_clean):
                stipend = ""
            # If it says "null" or "None" literally
            elif stipend_clean.lower() in ["null", "none", "n/a", "na", "not mentioned", "not specified"]:
                stipend = ""
        
        # --- FIX 2: DESCRIPTION CHECK ---
        # Reject posts that have no meaningful description/text
        post_text_raw = post.get("text", "") or ""
        if len(post_text_raw.strip()) < 30:
            print(f"    ❌ Skipped: No meaningful description (text too short)")
            continue
        
        # --- FIX 3: INDIA-ONLY LOCATION WHITELIST ---
        # Use a whitelist approach instead of a blacklist
        loc_lower = location.lower()
        india_keywords = [
            "india", "remote", "work from home", "wfh", "pan india",
            "bangalore", "bengaluru", "mumbai", "delhi", "new delhi",
            "gurgaon", "gurugram", "noida", "hyderabad", "chennai",
            "pune", "kolkata", "ahmedabad", "jaipur", "lucknow",
            "chandigarh", "indore", "kochi", "coimbatore", "nagpur",
            "bhopal", "visakhapatnam", "thiruvananthapuram", "surat",
            "vadodara", "mysore", "mangalore", "trivandrum",
            "guwahati", "bhubaneswar", "patna", "ranchi", "dehradun",
            "agra", "varanasi", "kanpur", "amritsar", "ludhiana",
            "rajkot", "jodhpur", "udaipur", "nashik", "aurangabad",
            "hubli", "madurai", "tiruchirappalli", "salem", "warangal",
            "vijayawada", "guntur", "nellore", "tirupati",
            "uttar pradesh", "maharashtra", "karnataka", "tamil nadu",
            "telangana", "andhra pradesh", "west bengal", "gujarat",
            "rajasthan", "madhya pradesh", "kerala", "haryana",
            "punjab", "bihar", "odisha", "jharkhand", "assam",
            "uttarakhand", "goa", "himachal pradesh",
        ]
        
        is_india = False
        if not loc_lower or loc_lower in ["unknown", ""]:
            # No location specified — check post text for India signals
            text_lower = post_text_raw.lower()
            is_india = any(kw in text_lower for kw in india_keywords)
        else:
            is_india = any(kw in loc_lower for kw in india_keywords)
        
        if not is_india:
            print(f"    ❌ Skipped (India whitelist): Location '{location}' is not India")
            continue
        
        # --- FIX 4: DEADLINE CAP (5 DAYS MAX) ---
        # If deadline is in the past or more than 5 days away, clear it
        if deadline:
            deadline_clean = deadline.strip().lower()
            if deadline_clean in ["null", "none", "n/a", "na", "not mentioned", "not specified"]:
                deadline = ""
            else:
                # Try to parse the deadline date
                try:
                    # Try common formats
                    parsed_deadline = None
                    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"]:
                        try:
                            parsed_deadline = datetime.strptime(deadline.strip(), fmt)
                            break
                        except ValueError:
                            continue
                    
                    if parsed_deadline:
                        today = datetime.now()
                        max_deadline = today + timedelta(days=5)
                        if parsed_deadline < today:
                            deadline = ""  # Past deadline, clear it
                        elif parsed_deadline > max_deadline:
                            deadline = ""  # Too far in future, clear it
                except Exception:
                    pass  # Can't parse, keep as-is
        
        # Role Splitting
        roles = analysis.get("roles") or [analysis.get("role", "Internship")]
        if isinstance(roles, str):
            roles = [roles]
        roles = [r for r in roles if r and r.strip()]
        if not roles: roles = ["Internship"]
        
        for role in roles:
            entry = dict(post)  # shallow copy
            entry["role"] = role.strip()
            entry["company"] = company
            entry["location"] = location
            entry["type"] = type_str
            entry["timing"] = timing
            entry["stipend"] = stipend
            entry["duration"] = duration
            entry["experience"] = experience
            entry["deadline"] = deadline
            entry["tags"] = tags if isinstance(tags, list) else []
            entry["contact_email"] = contact_email
            entry["apply_link"] = apply_link
            entry["work_type"] = timing # Map timing to legacy work_type for compatibility
            analyzed.append(entry)
            print(f"    ✅ {role.strip()} @ {company or 'Unknown'} | {location or 'N/A'} | stipend={stipend or 'N/A'}")
            
        time.sleep(REQUEST_DELAY)
        
    return analyzed

def filter_posts_with_llm(posts: list) -> list:
    return batch_analyze_posts(posts)

