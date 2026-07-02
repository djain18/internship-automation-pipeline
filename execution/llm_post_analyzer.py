"""
llm_post_analyzer.py
--------------------
Uses OpenAI (GPT-4o-mini), Gemini, or Groq (Llama 3.1 70B) to analyze LinkedIn posts.
Prioritizes OpenRouter/Gemini if keys are present.
"""

import logging
import os
import re
import json
import time
import concurrent.futures
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

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
    import importlib
    importlib.util.find_spec("groq")
    GROQ_AVAILABLE = importlib.util.find_spec("groq") is not None
except Exception:
    pass

# Gemini conditionally — use new google.genai SDK (google-generativeai is deprecated)
GEMINI_AVAILABLE = False
try:
    from google import genai as google_genai
    GEMINI_AVAILABLE = True
except ImportError:
    pass

# Defaults
PROVIDER = "none"
CLIENT = None
MODEL = "none"
REQUEST_DELAY = 1.0 

def analyze_post_regex(post_text: str, posted_time_str: str = None) -> dict:
    """Analyze post using Regex (Fallback for when LLMs are down)."""
    text_lower = post_text.lower()
    
    # 1. Freshness (Simple parsing)
    is_fresh = True
    age_days = 0
    if posted_time_str:
        if "mo" in posted_time_str or "yr" in posted_time_str:
            is_fresh = False
            age_days = 30
        elif "w" in posted_time_str:
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
    role_matches = re.findall(r'(?:hiring|looking) for ([\w\s]+?)(?:intern|internship)', text_lower)
    if role_matches:
        roles = [r.strip().title() + " Intern" for r in role_matches[:2]]
    
    if not roles:
        keywords = ["marketing", "finance", "sales", "hr", "operations", "tech", "data", "software", "business development", "product", "design", "graphic", "content"]
        for kw in keywords:
            if kw in text_lower and "intern" in text_lower:
                roles.append(kw.title() + " Intern")
                
    if not roles:
        roles = ["Internship"]
        
    # 3. Company
    company = ""
    at_match = re.search(r'\bat ([A-Z][\w\s\.]+?)(?:\.|,|\n| is| hiring| looking|!)', post_text)
    if at_match and len(at_match.group(1)) < 30:
        cand = at_match.group(1).strip()
        if cand.lower() not in ["the", "a", "an", "this", "my", "our", "least", "target", "all"]:
            company = cand
            
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
        
    return {
        "is_fresh": is_fresh,
        "age_days_estimate": age_days,
        "age_explanation": "Regex parsed",
        "roles": roles,
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
    
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and OPENAI_AVAILABLE:
        print("✅ Using OpenRouter (gpt-oss-120b) - EXTRACTION ONLY")
        PROVIDER = "openai"
        CLIENT = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
            timeout=30.0
        )
        MODEL = "openai/gpt-oss-120b"
        REQUEST_DELAY = 1.0
        return

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and GEMINI_AVAILABLE:
        print("✅ Using Gemini (gemini-2.0-flash-lite) - EXTRACTION ONLY")
        PROVIDER = "gemini"
        # New google.genai SDK
        CLIENT = google_genai.Client(api_key=gemini_key)
        MODEL = "gemini-2.0-flash-lite"
        REQUEST_DELAY = 1.0
        return
        
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and OPENAI_AVAILABLE:
        print("✅ Using OpenAI (gpt-4o-mini)")
        PROVIDER = "openai"
        CLIENT = OpenAI(api_key=openai_key, timeout=30.0)
        MODEL = "gpt-4o-mini"
        REQUEST_DELAY = 0.5
        return
    
    print("⚠️ Using Regex Analysis (Raw Code) - No AI, extracting patterns...")
    PROVIDER = "regex"
    REQUEST_DELAY = 0.0
    return

def analyze_post(client, post_text: str, current_date: str = None) -> dict:
    """Analyze post using configured LLM."""
    if not current_date:
        current_date = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""Extract structured data from this LinkedIn post.

TEXT: {post_text[:3000]}

EXTRACT the following fields from the post. Be accurate — only extract what is explicitly stated.

--- CLASSIFICATION RULES ---
- IS_HIRING_POST: Set should_include to true ONLY if the post is a specific recruitment notice for an ACTUAL opening.
- REJECT (should_include = false) if ANY of the following are true:
    - A full-time or permanent job opening without an internship component.
    - A generic "Recruiter seeking candidates" post without a specific single role or specific company link.
    - A post saying "DM me" or "Comment 'Interested'" without any email or apply URL.
    - A career coach giving advice or a "I'm hiring for 50 companies" promo.
    - A personal achievement/story or internship completion certificate.
    - A candidate looking for a job ("I am looking for", "seeking opportunities", "open to work").
    - PAY-TO-WORK SCAM: Post asks candidates to pay ANY fee — registration fee, training fee, security deposit, caution money, certification fee. REJECT IMMEDIATELY.
    - SCAM PATTERNS: "typing job", "data entry job", "form filling", "copy paste work", "earn ₹X daily", "guaranteed income", "100% genuine opportunity", "simple work from home", "no investment needed earn daily".
    - INTERNATIONAL ROLE: The internship is based outside India (USA, UK, Europe, UAE, Australia, Canada, Singapore, Korea, etc.) with NO India office option. "Remote" global roles are fine ONLY if the post explicitly mentions India eligibility or is from an Indian company.
---------------------------

1. COMPANY: The company or organization that is hiring.
   - Look for company names mentioned in the post text.
   - If the post says "at [Company]" or "[Company] is hiring", extract that name.
   - Remove domain extensions (.com, .in, .io) from company names.
   - If truly no company is mentioned anywhere, output "Unknown".

2. ROLES: List ALL specific internship role names mentioned.
   - EXCLUDE full-time/permanent jobs.
   - ALWAYS include the word "Intern" or "Internship" in the role name (e.g. "Frontend Developer" -> "Frontend Developer Intern") so it's clearly marked.
   - If multiple roles, split into array: ["Marketing Intern", "Sales Intern"]
   - If only generic "intern" or "internship" is mentioned, output ["Internship"]

3. LOCATION: City, state, or "Remote" / "Work From Home".
   - Extract the specific city/state if mentioned.
   - If "remote" or "work from home" or "WFH", output "Remote".
   - If multiple cities mentioned, list up to 2 separated by comma.
   - If no location is mentioned at all, output "Unknown".

4. TYPE: Output exactly one of: "Remote", "Hybrid", "Onsite", or null.

5. TIMING: Output exactly one of: "Full-time", "Part-time", or null.

6. STIPEND: Extract stipend/salary details. Output null if missing.
   - CRITICAL: Do NOT confuse years (2025, 2026, 2027) with stipend amounts.
   - Only extract actual monetary amounts or keywords like "paid", "unpaid".

7. DURATION: Extract internship duration (e.g. "3 months", "6 months"). Output null if missing.

8. EXPERIENCE: Extract required experience (e.g. "Fresher", "2024 graduate"). Output null if missing.

9. DEADLINE: Extract the application deadline date or time if present. Output null if missing.

10. TAGS: Output an array of up to 3 categorical tags (e.g. ["Engineering", "Python", "Startup"]).

11. CONTACT_EMAIL: Extract any email address mentioned in the post. Empty string if none.

12. APPLY_LINK: Extract the specific URL/link mentioned for applying. 
    - CRITICAL: Ignore generic resume building links (e.g., resume.io, enhancv).
    - Prioritize direct company application URLs, Google Forms, or recruiting platforms (Ashby, Greenhouse, Lever).
    - Empty string if none.

13. FORMATTED_DESCRIPTION: Rewrite the post as a clean, structured description using this EXACT format (omit any line if info is not available):

[2 to 4 line summary of the internship and the core work involved.]

- Role: [Job description/role details]
- Eligibility: [Eligibility, academic requirements, or specific candidate criteria]
- Stipend: [Amount/Paid/Unpaid]
- Duration: [Duration if mentioned]
- Work Type: [Onsite / Remote / Hybrid]
- Location: [City/States]
- [Include any other specific details from the post like Requirements, Tech Stack, or Benefits as individual bullet points.]
- Contact: [All essential contact details like Email, Phone, WhatsApp, etc.]

    RULES:
    - MAXIMUM LENGTH: STRICTLY under 1500 characters total.
    - REMOVE the Apply Link from this description entirely.
    - If a field is not specified in the post, COMPLETELY REMOVE that line from the description. Do NOT write "Not specified", "N/A", or "Unknown". (e.g. if Stipend is not mentioned, do not output the Stipend bullet point at all).
    - Use plain text. No markdown asterisks or bolding.
    - No emojis at all — strip them.
    - Do NOT include hashtags, "DM me", or vague CTAs.


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
    "formatted_description": "string",
    "should_include": boolean,
    "exclude_reason": "string (briefly why if should_include is false)"
}}
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            content = ""
            if PROVIDER == "gemini":
                # New google.genai SDK — strict 45s timeout
                from google.genai import types as genai_types
                response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        http_options=genai_types.HttpOptions(timeout=45000)  # ms
                    )
                )
                content = response.text
                
            elif PROVIDER in ["openai", "groq"]:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    timeout=45.0 # Strict 45s timeout
                )
                content = response.choices[0].message.content
            
            if not content:
                raise ValueError("Empty response from LLM")            # Clean markdown
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
                
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning("JSON parse failed: %s | content: %.100s", e, content)
                return {}
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                logger.error("LLM error (%s): %s", PROVIDER, e)
                return {"should_include": False, "exclude_reason": f"Error: {e}"}
    return {}

def batch_analyze_posts(posts: list) -> list:
    """Analyze a batch of posts with strict hiring classification."""
    if not CLIENT:
        configure_llm()
    if not CLIENT:
        return []
        
    analyzed = []
    print(f"Analyzing {len(posts)} posts with {PROVIDER} ({MODEL}) concurrently...")

    def process_post(args):
        i, post = args
        text = post.get("text", "")
        if not text: return []
        
        safe_text = text[:50].replace('\n', ' ')
        print(f"  [{i+1}/{len(posts)}] Processing: {safe_text}...")
        
        if PROVIDER == "regex":
             analysis = analyze_post_regex(text, post.get("posted_time"))
        else:
             if MODEL and "free" in MODEL:
                 time.sleep(8.0)
             analysis = analyze_post(CLIENT, text)
        
        post["llm_analysis"] = analysis
        
        # 1. HONOR LLM IRRELEVANCE FLAG
        if not analysis.get("should_include", True):
            reason = analysis.get("exclude_reason", "LLM judged irrelevant (Experience sharing/Personal story)")
            print(f"    ❌ [{i+1}/{len(posts)}] Rejected: {reason}")
            return []

        # 2. SECONDARY SCAM FILTER — catches what LLM misses
        _SCAM_PATTERNS = [
            "registration fee", "reg fee", "registration charges",
            "training fee", "training charges", "training cost",
            "security deposit", "caution money", "certification fee",
            "pay to join", "pay to work", "investment required",
            "typing job", "data entry job", "form filling job", "copy paste job",
            "earn daily", "earn per day", "easy money", "work from home earn",
            "100% genuine", "guaranteed income", "guaranteed placement",
            "whatsapp to register", "whatsapp registration",
            "simple typing", "home based typing",
        ]
        _text_scam = text.lower()
        _scam_hit = next((kw for kw in _SCAM_PATTERNS if kw in _text_scam), None)
        if _scam_hit:
            print(f"    ❌ [{i+1}/{len(posts)}] Rejected: Scam pattern ('{_scam_hit}')")
            return []

        company = (analysis.get("company", "") or "Unknown").strip()

        # Clean company name
        if ".com" in company.lower() or "www." in company.lower() or "http" in company.lower():
            try:
                clean_name = re.sub(r'https?://|www\.', '', company).split('/')[0]
                clean_name = clean_name.replace('.com', '').replace('.in', '').replace('.co', '')
                company = clean_name.title()
            except: pass

        # 3. COMPANY BLACKLIST — known international spam companies that flood LinkedIn
        _COMPANY_BLACKLIST = [
            "gao group", "gaotek", "gao tek", "gaо tek",  # Canadian company, irrelevant to India
        ]
        _company_norm = company.lower().strip()
        if any(bl in _company_norm for bl in _COMPANY_BLACKLIST):
            print(f"    ❌ [{i+1}/{len(posts)}] Rejected: Blacklisted company ({company})")
            return []

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

        # Minimum signal to be considered a real job post
        roles = analysis.get("roles") or [analysis.get("role", "Internship")]
        if isinstance(roles, str): roles = [roles]
        roles = [r for r in roles if r and r.strip()]
        if not roles: roles = ["Internship"]

        hiring_signal = 0
        has_specific_role = any(r.lower() not in ["internship", "intern", "hiring", "role", "unknown"] for r in roles)
        if company and company.lower() != "unknown": hiring_signal += 2
        if has_specific_role: hiring_signal += 2

        # MUST HAVE EITHER EMAIL OR APPLY LINK TO BE READY
        if contact_email or apply_link:
            hiring_signal += 2
        else:
            hiring_signal -= 2 # Penalty for "DM me" style posts

        # Keywords booster
        text_lower = text.lower()
        if any(w in text_lower for w in ["hiring", "openings", "recruiting", "vacancy", "join our team", "apply here"]):
            hiring_signal += 1

        if hiring_signal < 3:
            print(f"    ❌ [{i+1}/{len(posts)}] Rejected: Low hiring signal (Score: {hiring_signal})")
            return []

        # 4. INDIA LOCATION CHECK (fixed: "Remote" alone does NOT mean India)
        _INDIA_CITIES = [
            "india", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi",
            "gurgaon", "gurugram", "noida", "hyderabad", "chennai", "pune",
            "kolkata", "ahmedabad", "jaipur", "lucknow", "chandigarh", "indore",
            "kochi", "coimbatore", "nagpur", "bhopal", "visakhapatnam",
            "thiruvananthapuram", "surat", "vadodara", "mysore", "mangalore",
            "pan india", "wfh",
        ]
        _OUTSIDE_INDICATORS = [
            "usa", "uk", "london", "new york", "san francisco", "los angeles",
            "dubai", "uae", "australia", "canada", "germany", "singapore",
            "hong kong", "europe", "united states", "united kingdom", "korea",
            "japan", "china", "malaysia", "netherlands", "france", "italy",
            "toronto", "sydney", "berlin", "amsterdam", "paris", "seoul",
            "riyadh", "kuwait", "qatar", "bahrain", "oman",
        ]

        loc_lower = location.lower()
        text_lower = text.lower()

        # Hard reject: location explicitly says outside India (and not a dual-office with India)
        is_outside = any(kw in loc_lower for kw in _OUTSIDE_INDICATORS)
        if is_outside and "india" not in loc_lower:
            print(f"    ❌ [{i+1}/{len(posts)}] Rejected: International role ({location})")
            return []

        # Check if location mentions a specific Indian city
        is_india_loc = any(kw in loc_lower for kw in _INDIA_CITIES)

        # "Remote" location alone: must verify India context in post text
        is_remote_only = "remote" in loc_lower and not is_india_loc
        if is_remote_only:
            _india_text_kw = [
                "india", "bangalore", "bengaluru", "mumbai", "delhi",
                "hyderabad", "pune", "noida", "gurgaon", "chennai",
                "kolkata", "ahmedabad", "jaipur", "pan india",
                "indian students", "for india", "in india", "indian candidates",
            ]
            if not any(kw in text_lower for kw in _india_text_kw):
                print(f"    ❌ [{i+1}/{len(posts)}] Rejected: Remote with no India context")
                return []
        elif not is_india_loc and "remote" not in loc_lower:
            # Unknown/empty location — check post text as last resort
            _india_text_kw = [
                "india", "bangalore", "bengaluru", "mumbai", "delhi",
                "hyderabad", "pune", "noida", "gurgaon", "chennai",
                "kolkata", "ahmedabad", "jaipur", "pan india",
            ]
            if not any(kw in text_lower for kw in _india_text_kw):
                print(f"    ❌ [{i+1}/{len(posts)}] Rejected: No India context ({location or 'unknown'})")
                return []

        formatted_description = analysis.get("formatted_description", "") or ""

        local_results = []
        for role in roles:
            entry = dict(post)
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
            entry["formatted_description"] = formatted_description
            local_results.append(entry)
            print(f"    ✅ [{i+1}/{len(posts)}] Ready: {role.strip()} @ {company}")
            
        return local_results

    # --- Concurrent processing ---
    # Re-introducing ThreadPoolExecutor for speed as requested. 
    # Using a try-except block to handle KeyboardInterrupt (SIGINT) gracefully 
    # to avoid the crash observed in previous cloud runs.
    
    workers = 10 # Slightly reduced from 15 to ensure stability in cloud
    if MODEL and "free" in MODEL:
        workers = 1 # Safety for free models
        
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        # Submit all posts to the executor
        future_to_post = {executor.submit(process_post, (i, post)): i for i, post in enumerate(posts)}
        
        # Collect results as they complete
        # 900s (15 min) timeout per batch — avoids premature truncation on large batches
        for future in concurrent.futures.as_completed(future_to_post, timeout=900):
            try:
                # 90s per individual result — generous but bounded
                res = future.result(timeout=90) 
                if res:
                    analyzed.extend(res)
            except concurrent.futures.TimeoutError:
                idx = future_to_post[future]
                print(f"    ⚠️  [{idx+1}/{len(posts)}] Individual request timed out (90s). Skipping.")
            except Exception as e:
                idx = future_to_post[future]
                print(f"    ⚠️  [{idx+1}/{len(posts)}] Future failed: {e}")
                
    except KeyboardInterrupt:
        print(f"\n🛑 KeyboardInterrupt caught! Modal might be terminating the container (OOM or Timeout). Saving {len(analyzed)} results...")
        executor.shutdown(wait=False, cancel_futures=True)
    except concurrent.futures.TimeoutError:
        print(f"\n🛑 Batch Timeout reached (600s)! Saving {len(analyzed)} results...")
        executor.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        print(f"\n🛑 CRITICAL BATCH ERROR: {e}")
        executor.shutdown(wait=False, cancel_futures=True)
    finally:
        # Final safety shutdown
        executor.shutdown(wait=False, cancel_futures=True)

    return analyzed

def filter_posts_with_llm(posts: list) -> list:
    return batch_analyze_posts(posts)
