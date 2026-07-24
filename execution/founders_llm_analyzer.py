"""
founders_llm_analyzer.py
-------------------------
LLM screener for Daksh's personal Founder's Office / AI Automation / GTM
Engineer job search feed. Same provider cascade as llm_post_analyzer.py
(OpenRouter -> Gemini -> OpenAI -> Groq -> regex) but a different prompt/schema:
judges role-track fit, company AI-relevance, and seniority — none of which the
RISE internship screener needs.
"""
import logging
import os
import json
import time
import concurrent.futures
from dotenv import load_dotenv

try:
    from execution import founders_role_filter as ff
except ImportError:
    import founders_role_filter as ff

logger = logging.getLogger(__name__)
load_dotenv()

OPENAI_AVAILABLE = False
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    pass

GEMINI_AVAILABLE = False
try:
    from google import genai as google_genai
    GEMINI_AVAILABLE = True
except ImportError:
    pass

PROVIDER = "none"
CLIENT = None
MODEL = "none"


def configure_llm():
    global PROVIDER, CLIENT, MODEL
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and OPENAI_AVAILABLE:
        PROVIDER = "openai"
        CLIENT = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key, timeout=30.0)
        MODEL = "openai/gpt-oss-120b"
        return
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and GEMINI_AVAILABLE:
        PROVIDER = "gemini"
        CLIENT = google_genai.Client(api_key=gemini_key)
        MODEL = "gemini-2.0-flash-lite"
        return
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and OPENAI_AVAILABLE:
        PROVIDER = "openai"
        CLIENT = OpenAI(api_key=openai_key, timeout=30.0)
        MODEL = "gpt-4o-mini"
        return
    PROVIDER = "none"


PROMPT_TEMPLATE = """Extract structured data from this LinkedIn post for a PERSONAL job search
targeting Founder's Office / AI Automation / GTM Engineer roles at AI-focused startups.

TEXT: {post_text}

--- CLASSIFICATION RULES (be strict — this is a curated personal feed, not a broad board) ---
- ROLE_TRACK: classify the role into exactly one of:
    "founders_office" — Founder's Office, Chief of Staff, Founder's Associate, Business/Ops
                          generalist reporting directly to founders.
    "ai_automation"   — AI Automation Engineer, AI Ops, workflow/agent automation builder,
                          no-code/low-code AI automation roles.
    "gtm"             — GTM Engineer, Growth Engineer, RevOps Engineer, technical growth/
                          demand-gen roles (NOT plain sales/BDR with no technical component).
    "other"           — anything else (plain sales, generic marketing, unrelated engineering,
                          HR, finance, etc.) — REJECT these.
- AI_RELEVANCE: judge whether the HIRING COMPANY ITSELF is an AI/ML/LLM-focused product or
  startup (building AI models, AI agents, AI-native products) — NOT merely a company that
  uses AI tools internally. Output "strong" (clearly an AI company/product), "moderate"
  (AI-adjacent / AI is a real part of the product), or "none" (not AI-focused at all).
  This is informational only — AI focus is PREFERRED but NOT a reason to reject a post.
  A genuine Founder's Office / AI Automation / GTM role at a non-AI company still counts.
- SENIORITY: reject SENIOR / STAFF / PRINCIPAL / DIRECTOR / LEAD / MANAGER postings or any
  posting explicitly requiring 4+ years of experience. We want INTERNSHIP, entry-level,
  associate, or early-career full-time roles only.
- REJECT (should_include = false) if ANY of the following:
    - AGGREGATOR / REPOSTER: author is a job-alert/off-campus/placement page or the post
      lists many roles at once ("multiple positions", "20+ openings"), or is a paid-
      mentorship/referral promo, or asks to "tag/share/join our WhatsApp/Telegram group".
    - APPLY-BY-CHAT: the only way to apply is WhatsApp, Telegram, "DM me", or "comment
      Interested".
    - A full-time senior/staff/lead/director posting (see SENIORITY above).
    - LOCATION MISMATCH: onsite/hybrid role in any Indian city other than Bengaluru/
      Bangalore. Remote is fine only if India-eligible.
    - PAY-TO-WORK SCAM or generic scam patterns (registration fee, "earn daily", etc).
    - Role track is "other" (not Founder's Office / AI Automation / GTM).
---------------------------

1. COMPANY: the hiring company/organization. "Unknown" if truly not mentioned.
2. ROLES: array of specific role title(s) mentioned (e.g. ["GTM Engineer Intern"]).
3. LOCATION: city or "Remote"/"WFH". "Unknown" if not mentioned.
4. TYPE: "Remote" | "Hybrid" | "Onsite" | null.
5. TIMING: "Full-time" | "Part-time" | "Internship" | null.
6. STIPEND: stipend/salary details, or null.
7. DURATION: internship duration if applicable, or null.
8. EXPERIENCE: required experience/seniority text, or null.
9. DEADLINE: application deadline if present, or null.
10. TAGS: up to 3 short tags (e.g. ["AI Startup", "GTM", "Series A"]).
11. CONTACT_EMAIL: any email mentioned, or empty string.
12. APPLY_LINK: the specific apply URL (ATS/careers/form). Empty string if none.
13. ROLE_TRACK: "founders_office" | "ai_automation" | "gtm" | "other".
14. AI_RELEVANCE: "strong" | "moderate" | "none".
15. IS_AGGREGATOR_REPOST: true/false (see rules above).
16. APPLY_METHOD: "ats" | "form" | "company_email" | "personal_email" | "whatsapp" | "dm_comment" | "none".
17. COMPANY_LEGITIMACY: "established" | "plausible_startup" | "doubtful".
18. GENUINENESS_SCORE: integer 0-100 (be strict — aggregators/chat-apply/doubtful score under 40).
19. FORMATTED_DESCRIPTION: 2-4 line summary + bullet points (Role/Eligibility/Stipend/
    Duration/Work Type/Location/Contact), plain text, no markdown, under 1500 chars,
    omit any line with no info, no "DM me"/hashtags/emojis, remove apply link from text.

Output JSON:
{{
    "company": "string", "roles": ["string"], "location": "string",
    "type": "Remote | Hybrid | Onsite | null", "timing": "string or null",
    "stipend": "string or null", "duration": "string or null",
    "experience": "string or null", "deadline": "string or null",
    "tags": ["string"], "contact_email": "string or empty", "apply_link": "string or empty",
    "role_track": "founders_office | ai_automation | gtm | other",
    "ai_relevance": "strong | moderate | none",
    "is_aggregator_repost": boolean,
    "apply_method": "ats | form | company_email | personal_email | whatsapp | dm_comment | none",
    "company_legitimacy": "established | plausible_startup | doubtful",
    "genuineness_score": integer,
    "formatted_description": "string",
    "should_include": boolean,
    "exclude_reason": "string"
}}
"""


def analyze_post(client, post_text: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(post_text=post_text[:3000])
    max_retries = 3
    for attempt in range(max_retries):
        try:
            content = ""
            if PROVIDER == "gemini":
                from google.genai import types as genai_types
                response = client.models.generate_content(
                    model=MODEL, contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        http_options=genai_types.HttpOptions(timeout=45000),
                    ),
                )
                content = response.text
            elif PROVIDER == "openai":
                response = client.chat.completions.create(
                    model=MODEL, messages=[{"role": "user", "content": prompt}],
                    temperature=0.1, response_format={"type": "json_object"}, timeout=45.0,
                )
                content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from LLM")
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
    """Analyze posts concurrently, applying founders_role_filter.evaluate_founders_post."""
    if not CLIENT:
        configure_llm()
    if not CLIENT:
        return []

    analyzed = []
    print(f"Analyzing {len(posts)} posts with {PROVIDER} ({MODEL})...")

    def process_post(args):
        i, post = args
        text = post.get("text", "")
        if not text:
            return None
        safe_text = text[:50].replace("\n", " ")
        print(f"  [{i+1}/{len(posts)}] Processing: {safe_text}...")
        analysis = analyze_post(CLIENT, text)
        post["llm_analysis"] = analysis

        if not analysis.get("should_include", True):
            reason = analysis.get("exclude_reason", "LLM judged irrelevant")
            print(f"    [X] [{i+1}/{len(posts)}] Rejected: {reason}")
            return None

        decision = ff.evaluate_founders_post(analysis, post)
        if not decision.get("accept"):
            print(f"    [X] [{i+1}/{len(posts)}] Rejected: {decision.get('reason')}")
            return None

        company = (analysis.get("company") or "Unknown").strip()
        roles = analysis.get("roles") or ["Role"]
        if isinstance(roles, str):
            roles = [roles]
        role = (roles[0] if roles else "Role").strip()

        entry = dict(post)
        entry["role"] = role
        entry["company"] = company
        entry["location"] = analysis.get("location") or ""
        entry["type"] = analysis.get("type") or ""
        entry["timing"] = analysis.get("timing") or ""
        entry["stipend"] = analysis.get("stipend") or ""
        entry["duration"] = analysis.get("duration") or ""
        entry["experience"] = analysis.get("experience") or ""
        entry["deadline"] = analysis.get("deadline") or ""
        entry["tags"] = analysis.get("tags") if isinstance(analysis.get("tags"), list) else []
        entry["contact_email"] = analysis.get("contact_email") or ""
        entry["apply_link"] = analysis.get("apply_link") or ""
        entry["formatted_description"] = analysis.get("formatted_description") or ""
        entry["role_track"] = decision.get("role_track", "")
        entry["ai_relevance"] = decision.get("ai_relevance", "none")
        print(f"    [OK] [{i+1}/{len(posts)}] Ready: {role} @ {company} "
              f"[{decision.get('role_track')}/{decision.get('ai_relevance')}]")
        return entry

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    try:
        futures = {executor.submit(process_post, (i, p)): i for i, p in enumerate(posts)}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=600):
                try:
                    res = future.result(timeout=90)
                    if res:
                        analyzed.append(res)
                except concurrent.futures.TimeoutError:
                    idx = futures[future]
                    print(f"    [!] [{idx+1}/{len(posts)}] Individual request timed out. Skipping.")
                except Exception as e:
                    idx = futures[future]
                    print(f"    [!] [{idx+1}/{len(posts)}] Failed: {e}")
        except concurrent.futures.TimeoutError:
            # Batch-level timeout: some futures never finished within 600s.
            # Don't lose what already completed — just stop waiting.
            print(f"    [!] Batch timeout reached — proceeding with {len(analyzed)} results collected so far.")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return analyzed
