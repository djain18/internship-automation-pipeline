"""
quality_filter.py
-----------------
Deterministic, unit-testable anti-spam + relevance gate for internship posts.

This is the single source of truth for "is this a genuine internship we want?"
It is imported by BOTH scrape_linkedin_posts.py (pre-LLM + post-LLM) and
llm_post_analyzer.py, so the rules can never drift apart again.

Design philosophy (see CLAUDE.md): the LLM extracts/labels; THIS CODE decides.
Quality-first: when a signal is ambiguous, we drop rather than pad.

Policy (locked with product owner, 2026-07; location widened 2026-07-27,
widened again to all-India 2026-08-21):
  - Location: Remote (India-eligible) accepted from anywhere; onsite/hybrid
    accepted anywhere in India in ACCEPTED_CITY_TERMS (metros plus a broad
    set of tier-2/3 cities and state capitals). Only explicitly foreign
    locations, or posts with no recognizable location signal at all, are
    dropped.
  - Aggregator/reposter "multiple positions" lists + paid-mentorship promos: DROP.
  - Apply-via WhatsApp / DM / "comment interested": DROP (no real application).
  - Unpaid TECH roles: DROP. Unpaid non-tech: keep, but flagged.
  - No hard nightly quota — publish only what clears the bar.

Every public function returns plain data (bool / str / tuple) so it can be
tested without any network, LLM, or Google auth.
"""

import re

# ─────────────────────────────────────────────────────────────────────────────
# Location vocab
# ─────────────────────────────────────────────────────────────────────────────
# Onsite/hybrid accepted cities — all of India. Started as a Bengaluru-only
# gate, widened 2026-07-27 to the top 12 internship-volume metros, then widened
# again 2026-08-21 to a broad tier-2/3 list per product decision (a fixed metro
# whitelist structurally can't cover "roles across India") — see
# [[anti-spam-policy]]. Delhi, Gurgaon, and Noida are kept as separate entries
# (not merged into one "NCR" term) because posts name the specific city, not
# the region.
ACCEPTED_CITY_TERMS = (
    # Metros / original 12
    "bengaluru", "bangalore", "bangaluru", "blr",
    "mumbai", "bombay",
    "delhi", "new delhi",
    "gurgaon", "gurugram",
    "noida",
    "pune",
    "hyderabad",
    "chennai",
    "jaipur",
    "ahmedabad",
    "kolkata",
    "indore",
    # Tier-2/3 cities and state capitals
    "lucknow", "chandigarh", "kochi", "cochin", "coimbatore", "nagpur",
    "bhopal", "visakhapatnam", "vizag", "thiruvananthapuram", "trivandrum",
    "surat", "vadodara", "mysore", "mysuru", "mangalore", "mangaluru",
    "gandhinagar", "faridabad", "thane", "navi mumbai",
    "patna", "ranchi", "raipur", "bhubaneswar", "guwahati", "dehradun",
    "shimla", "jammu", "srinagar", "panaji", "goa",
    "imphal", "agartala", "aizawl", "kohima", "itanagar", "gangtok",
    "amritsar", "ludhiana", "jalandhar",
    "varanasi", "kanpur", "agra", "prayagraj", "allahabad", "meerut",
    "nashik", "aurangabad", "nagpur", "rajkot", "vijayawada", "warangal",
    "madurai", "tiruchirappalli", "trichy", "salem",
    "hubli", "dharwad", "belgaum", "belagavi",
    "jodhpur", "udaipur", "kota", "bikaner",
    "siliguri", "durgapur", "asansol", "cuttack",
    "jamshedpur", "dhanbad", "bhilai", "gwalior", "jabalpur", "ujjain",
    "pondicherry", "puducherry",
)
# Back-compat alias — some call sites/tests may still refer to the old name.
BENGALURU_TERMS = ("bengaluru", "bangalore", "bangaluru", "blr")

REMOTE_TERMS = ("remote", "work from home", "wfh", "work-from-home")

# Explicit foreign markers — a remote role that is foreign-ONLY is useless to an
# India-based candidate, so we still drop those.
FOREIGN_TERMS = (
    "usa", "u.s.", "us only", "us-only", "usa only", "united states",
    "uk only", "uk", "united kingdom", "london",
    "new york", "san francisco", "los angeles", "dubai", "uae", "abu dhabi",
    "australia", "canada", "germany", "singapore", "hong kong", "europe",
    "korea", "japan", "china", "malaysia", "netherlands", "france", "italy",
    "toronto", "sydney", "berlin", "amsterdam", "paris", "seoul", "riyadh",
    "kuwait", "qatar", "bahrain", "oman", "philippines", "vietnam", "indonesia",
)

INDIA_CONTEXT_TERMS = (
    "india", "indian", "bengaluru", "bangalore", "mumbai", "delhi",
    "hyderabad", "pune", "noida", "gurgaon", "gurugram", "chennai",
    "kolkata", "ahmedabad", "jaipur", "pan india", "pan-india",
    "for india", "in india", "across india", "₹", "inr", "rupees", "lpa", "lakh",
)

# ─────────────────────────────────────────────────────────────────────────────
# Tech-role vocab (used only to decide whether an UNPAID role gets dropped)
# ─────────────────────────────────────────────────────────────────────────────
TECH_ROLE_TERMS = (
    "software", "sde", "developer", "development intern", "frontend", "front-end",
    "front end", "backend", "back-end", "back end", "full stack", "fullstack",
    "full-stack", "web dev", "web developer", "app developer", "android",
    "ios", "mobile developer", "data science", "data scientist", "data analyst",
    "data engineer", "machine learning", " ml ", "ml intern", "ai intern",
    "ai/ml", "artificial intelligence", "devops", "cloud engineer", "qa engineer",
    "quality assurance", "sdet", "test engineer", "python developer",
    "java developer", "react", "node", "programmer", "coding", "engineering intern",
    "computer vision", "nlp", "blockchain", "cybersecurity", "security engineer",
)

# ─────────────────────────────────────────────────────────────────────────────
# Aggregator / reposter detection
# ─────────────────────────────────────────────────────────────────────────────
# Account names / headlines that scream "job aggregator influencer", not employer.
AGGREGATOR_AUTHOR_TERMS = (
    "job alert", "job alerts", "jobs alert", "job portal", "job board",
    "off campus", "offcampus", "off-campus", "fresher jobs", "freshers jobs",
    "fresher openings", "hiring alert", "hiring updates", "placement",
    "career crate", "worknation", "hiredinn", "jobs buzz", "job buzz",
    "jobsquad", "job squad", "careerz", "jobss", "vacancy", "we are hiring",
    "wearehiring", "hire dinn", "internship alert", "daily jobs", "jobify",
    "job updates", "hiring feed", "talent pool", "sarkari", "govt jobs",
    "jobs adda", "jobsadda", "job factory", "recruitment updates",
)

# Post-body patterns that indicate a bulk repost / promo rather than one opening.
AGGREGATOR_BODY_PATTERNS = (
    "hiring for multiple", "multiple positions", "multiple openings",
    "multiple roles", "20+ openings", "10+ openings", "50+ companies",
    "hiring for 50", "hiring for multiple companies", "off campus drive",
    "mega hiring", "mass hiring", "bulk hiring", "hiring across",
    "tag your friends", "tag someone", "share with your network",
    "share this post", "repost this", "comment interested and share",
    "resume fix", "resume review | ", "1:1 mentorship", "mentorship program",
    "referral | resume", "dm for referral", "dm me for referral",
    "join our whatsapp group", "join whatsapp group", "join our telegram",
    "join telegram", "join the community", "link in comment", "link in comments",
    "check the comment", "check comments",
)

# ─────────────────────────────────────────────────────────────────────────────
# Apply-method classification
# ─────────────────────────────────────────────────────────────────────────────
ATS_DOMAINS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "workday",
    "smartrecruiters.com", "zohorecruit", "keka.com", "freshteam.com",
    "wellfound.com", "angel.co", "instahyre.com", "cutshort.io", "hirist.com",
    "hirist.tech", "iimjobs.com", "darwinbox", "recruiterbox", "peoplehum",
    "jobvite.com", "icims.com", "taleo", "successfactors", "bamboohr.com",
    "workable.com", "recruitee.com", "breezy.hr", "manatal", "turbohire",
    "phenom", "eightfold", "oracle.com/careers",
)

FORM_DOMAINS = ("forms.gle", "docs.google.com/forms", "google.com/forms",
                "forms.office.com", "typeform.com", "airtable.com/shr",
                "tally.so", "jotform.com", "surveymonkey")

PERSONAL_EMAIL_DOMAINS = (
    "gmail.com", "yahoo.com", "yahoo.in", "yahoo.co.in", "hotmail.com",
    "outlook.com", "rediffmail.com", "rediff.com", "ymail.com", "live.com",
    "protonmail.com", "icloud.com", "gmx.com",
)

WHATSAPP_TERMS = ("whatsapp", "wa.me", "chat.whatsapp.com", "whatsap", "whats app",
                  "wtsp", "telegram", "t.me/")

# Known spam / mass-repost companies that flood LinkedIn with fake or
# perpetual-"internship" listings (rotate names, unpaid, no real work).
COMPANY_BLACKLIST = (
    "gaotek", "gao tek", "gao group", "gaogroup", "thegaogroup", "gao rfid",
    "gao embedded", "gao research", "gao usa", "gao inc",
)

DM_APPLY_PATTERNS = (
    "dm me", "dm us", "dm for", "drop a dm", "send a dm", "ping me",
    "comment interested", "comment 'interested'", "comment \"interested\"",
    "comment #interested", "comment your", "comment below and", "type interested",
    "reply interested", "comment 'yes'", "comment yes to",
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")


# ═════════════════════════════════════════════════════════════════════════════
# Public helpers
# ═════════════════════════════════════════════════════════════════════════════
def _norm(s) -> str:
    return (s or "").lower().strip()


def is_tech_role(role: str) -> bool:
    """True if the role is an engineering/data/ML-type technical internship."""
    r = f" {_norm(role)} "
    return any(term in r for term in TECH_ROLE_TERMS)


def is_unpaid(stipend: str, text: str = "") -> bool:
    """True if the post clearly offers no monetary stipend.

    Conservative: only returns True on explicit unpaid language OR an explicit
    zero. 'Not specified' / missing stipend is treated as unknown (not unpaid).
    """
    s = _norm(stipend)
    t = _norm(text)
    if any(kw in s for kw in ("unpaid", "no stipend", "not paid", "without stipend",
                              "0", "nil", "none")):
        # Guard: '10,000' contains no unpaid words; the '0' check needs the whole
        # field to be zero-ish, not merely contain a zero digit.
        if s in ("0", "0/month", "₹0", "nil", "none", "unpaid", "no stipend",
                 "not paid", "without stipend"):
            return True
        if "unpaid" in s or "no stipend" in s or "not paid" in s or "without stipend" in s:
            return True
    for kw in ("unpaid internship", "this is unpaid", "no stipend will be provided",
               "stipend: unpaid", "stipend - unpaid", "non-paid", "non paid",
               "unpaid but", "certificate only", "only certificate",
               "no monetary", "purely for experience", "purely learning",
               "experience certificate in lieu"):
        if kw in t:
            return True
    return False


def classify_apply_method(text: str, email: str = "", apply_link: str = "") -> str:
    """Return one of:
        'ats'            – applies via a real recruiting platform / careers page
        'form'           – Google/Office form (acceptable)
        'company_email'  – a non-personal-domain email
        'personal_email' – gmail/yahoo/etc (weak but allowed)
        'whatsapp'       – WhatsApp / Telegram apply (REJECT)
        'dm_comment'     – "DM me" / "comment interested" (REJECT)
        'none'           – no way to apply found (REJECT)
    Highest-quality signal present wins.
    """
    t = _norm(text)
    link = _norm(apply_link)
    blob = f"{t} {link} {_norm(email)}"

    # Positive signals first (a real ATS link overrides noise in the body).
    if any(d in blob for d in ATS_DOMAINS):
        return "ats"
    if any(d in blob for d in FORM_DOMAINS):
        return "form"

    # Collect emails from both the explicit field and the body.
    emails = []
    if email:
        emails += _EMAIL_RE.findall(email)
    emails += _EMAIL_RE.findall(text or "")
    emails = [e.lower() for e in emails
              if not e.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg"))]
    if emails:
        for e in emails:
            domain = e.split("@")[-1]
            if not any(domain == pd or domain.endswith("." + pd)
                       for pd in PERSONAL_EMAIL_DOMAINS):
                return "company_email"
        # only personal emails present
        return "personal_email"

    # Negative-only signals.
    if any(w in blob for w in WHATSAPP_TERMS):
        return "whatsapp"
    if any(p in t for p in DM_APPLY_PATTERNS):
        return "dm_comment"

    # A bare careers/apply URL with no ATS/form/email — treat as ATS-ish (real link).
    for url in _URL_RE.findall(apply_link or "") + _URL_RE.findall(text or ""):
        u = url.lower()
        if any(w in u for w in WHATSAPP_TERMS):
            continue
        if any(kw in u for kw in ("career", "careers", "/jobs", "/job/", "apply",
                                  "/hiring", "join", "work-with-us", "workwithus")):
            return "ats"
    return "none"


def is_aggregator_post(author_name: str = "", author_headline: str = "",
                       text: str = "", roles=None) -> tuple:
    """Detect job-aggregator / reposter / paid-mentorship-promo posts.

    Returns (is_aggregator: bool, reason: str).
    """
    name = _norm(author_name)
    headline = _norm(author_headline)
    body = _norm(text)
    who = f"{name} {headline}"

    for term in AGGREGATOR_AUTHOR_TERMS:
        if term in who:
            return True, f"aggregator account ('{term}')"

    for pat in AGGREGATOR_BODY_PATTERNS:
        if pat in body:
            return True, f"bulk-repost/promo pattern ('{pat}')"

    # A single post listing many distinct roles is an aggregator list, not one job.
    role_list = [r for r in (roles or []) if r and _norm(r) not in ("internship", "intern")]
    if len(role_list) >= 4:
        return True, f"lists {len(role_list)} roles (bulk post)"

    # Count "hiring:" style role enumerations in the body (e.g. "1. X 2. Y 3. Z").
    enumerated = len(re.findall(r"(?m)^\s*\d+[\.\)]\s+\w", text or ""))
    if enumerated >= 4:
        return True, f"{enumerated} enumerated openings (bulk post)"

    return False, ""


def location_decision(location: str, work_mode: str = "", text: str = "") -> tuple:
    """Accepted-city-onsite (all of India) OR India-eligible-remote gate.

    Returns (accept: bool, resolved_mode: str, reason: str)
      resolved_mode in {'remote', 'onsite', 'other'}
    Rules:
      - Remote (and not foreign-only)               → accept
      - Onsite/Hybrid in a recognized Indian city    → accept
      - Unknown but text shows remote/accepted-city  → accept
      - Otherwise (foreign, or no location signal)   → reject
    """
    loc = _norm(location)
    mode = _norm(work_mode)
    body = _norm(text)

    # The STRUCTURED fields (location + work_mode) are authoritative. A stray
    # "remote" in the body must NOT override an explicit "Nagpur / Onsite".
    loc_remote = any(t in loc for t in REMOTE_TERMS) or any(t in mode for t in REMOTE_TERMS)
    loc_accepted = any(t in loc for t in ACCEPTED_CITY_TERMS)

    foreign_present = any(f in loc for f in FOREIGN_TERMS) or \
        any(f in body for f in FOREIGN_TERMS)
    india_ctx = any(t in loc or t in body for t in INDIA_CONTEXT_TERMS) or loc_accepted

    # 1) Explicit remote in the structured fields → accept unless foreign-only.
    if loc_remote:
        if foreign_present and not india_ctx:
            return False, "remote", "remote but foreign-only (no India eligibility)"
        return True, "remote", "remote / India-eligible"

    # 2) Explicit accepted (Indian) city in the location field → accept.
    if loc_accepted:
        return True, "onsite", "onsite accepted city"

    # 3) Explicit foreign location, no remote → reject. This comes BEFORE any
    #    body scan so a body "remote" mention can't rescue it.
    if foreign_present and not india_ctx:
        return False, "other", f"onsite foreign location ({location})"

    # 4) Location field empty/unknown → fall back to the body as last resort.
    body_accepted = any(t in body for t in ACCEPTED_CITY_TERMS)
    body_remote = bool(re.search(r"\bremote\b", body)) or bool(re.search(r"\bwfh\b", body)) \
        or "work from home" in body
    if body_accepted:
        return True, "onsite", "accepted city (from post text)"
    if body_remote:
        if foreign_present and not india_ctx:
            return False, "remote", "remote but foreign-only (no India eligibility)"
        return True, "remote", "remote / India-eligible (from post text)"

    return False, "other", "location not an accepted city/remote (unconfirmed)"


def evaluate_post(analysis: dict, post: dict) -> dict:
    """Final deterministic gate combining every rule above.

    `analysis`  – the LLM (or regex) extraction for this post.
    `post`      – the raw scraped post (for author + full text).

    Returns:
        {
          "accept": bool,
          "reason": str,          # why rejected (empty if accepted)
          "score": int,           # 0-100 genuineness score (for ranking/logging)
          "apply_method": str,
          "resolved_mode": str,   # remote / onsite / other
          "unpaid_flag": bool,    # accepted-but-unpaid (non-tech)
        }
    """
    text = (post.get("text") or post.get("postText") or post.get("content")
            or post.get("post_text") or "")
    author_name = (post.get("authorName") or post.get("author_name")
                   or (post.get("author") or {}).get("name") if isinstance(post.get("author"), dict) else post.get("author_name")) or ""
    author_headline = (post.get("authorHeadline") or post.get("author_headline") or "")

    roles = analysis.get("roles") or ([analysis.get("role")] if analysis.get("role") else [])
    if isinstance(roles, str):
        roles = [roles]
    roles = [r for r in roles if r]
    primary_role = roles[0] if roles else (analysis.get("role") or "Internship")

    location = analysis.get("location") or post.get("location") or ""
    work_mode = analysis.get("type") or post.get("type") or analysis.get("work_type") or ""
    stipend = analysis.get("stipend") or post.get("stipend") or ""
    email = analysis.get("contact_email") or post.get("contact_email") or ""
    apply_link = analysis.get("apply_link") or post.get("apply_link") or ""
    company = _norm(analysis.get("company") or post.get("company") or "")

    result = {
        "accept": False, "reason": "", "score": 0,
        "apply_method": "none", "resolved_mode": "other", "unpaid_flag": False,
    }

    # 1) Aggregator / reposter / promo → hard drop.
    is_agg, agg_reason = is_aggregator_post(author_name, author_headline, text, roles)
    # Trust an explicit LLM aggregator flag too.
    if analysis.get("is_aggregator_repost") is True:
        is_agg, agg_reason = True, "LLM flagged aggregator repost"
    if is_agg:
        result["reason"] = agg_reason
        return result

    # 1b) Blacklisted spam company (GAOTEK & friends) — check company name,
    #     apply email/link domain, and author.
    _bl_blob = " ".join([
        company,
        _norm(analysis.get("contact_email") or post.get("contact_email") or ""),
        _norm(analysis.get("apply_link") or post.get("apply_link") or ""),
        _norm(author_name), _norm(author_headline),
    ])
    if any(bl in _bl_blob for bl in COMPANY_BLACKLIST):
        result["reason"] = "blacklisted spam company"
        return result

    # 2) Apply method → drop WhatsApp / DM / none.
    method = classify_apply_method(text, email, apply_link)
    # Let the LLM override to a WORSE class only (never upgrade a bad method).
    llm_method = _norm(analysis.get("apply_method"))
    if llm_method in ("whatsapp", "dm_comment", "none") and method in ("personal_email", "form"):
        method = llm_method
    result["apply_method"] = method
    if method in ("whatsapp", "dm_comment"):
        result["reason"] = f"apply via {method.replace('_', '/')}"
        return result
    if method == "none":
        result["reason"] = "no application method"
        return result

    # 3) Location gate.
    accept_loc, mode, loc_reason = location_decision(location, work_mode, text)
    result["resolved_mode"] = mode
    if not accept_loc:
        result["reason"] = loc_reason
        return result

    # 4) Unpaid TECH → drop. Unpaid non-tech → keep but flag.
    unpaid = is_unpaid(stipend, text)
    if analysis.get("is_paid") == "no":
        unpaid = True
    tech = is_tech_role(primary_role) or _norm(analysis.get("field_type")) == "tech"
    if unpaid and tech:
        result["reason"] = "unpaid tech role"
        return result
    result["unpaid_flag"] = bool(unpaid)

    # 4b) LLM trust signals — the positive-legitimacy check (guards against a
    # well-disguised fake that passes every negative filter above).
    legitimacy = _norm(analysis.get("company_legitimacy"))
    weak_apply = method in ("personal_email", "form")
    if legitimacy == "doubtful" and weak_apply:
        result["reason"] = "doubtful company + weak apply channel"
        return result
    gscore = analysis.get("genuineness_score")
    try:
        gscore = int(gscore)
    except (TypeError, ValueError):
        gscore = None
    if gscore is not None and gscore < 35:
        result["reason"] = f"low genuineness score ({gscore})"
        return result

    # 5) Passed every gate → compute a genuineness score for ranking.
    score = 40
    if company and company not in ("unknown", ""):
        score += 15
    if method == "ats":
        score += 25
    elif method == "company_email":
        score += 18
    elif method == "form":
        score += 10
    elif method == "personal_email":
        score += 4
    if any(is_tech_role(r) is False for r in roles):  # has a concrete titled role
        pass
    if primary_role and _norm(primary_role) not in ("internship", "intern"):
        score += 8
    if not unpaid:
        score += 8
    if mode == "onsite":
        score += 4  # slight preference: confirmed accepted-city onsite
    result["score"] = min(100, score)
    result["accept"] = True
    return result
