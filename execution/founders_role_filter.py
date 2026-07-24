"""
founders_role_filter.py
-----------------------
Deterministic gate for Daksh's PERSONAL job search feed: Founder's Office /
AI Automation / GTM Engineer roles at AI-focused startups. Separate from
quality_filter.py (which governs the public RISE internship sheet), but reuses
its aggregator / apply-method / location / blacklist primitives — those
anti-spam rules don't change just because the feed does.

Policy (locked 2026-07-22, see ai executive assistant/career/CLAUDE.md):
  - Role must be Founder's Office, AI Automation, or GTM/Growth Engineer track.
  - Company must be AI/ML-focused (per Daksh's stated "AI companies only"
    targeting strategy) — not merely a company that happens to use AI tools.
  - Entry-level / internship / associate / APM-style only — reject senior,
    staff, director, lead, or "N+ years experience" postings.
  - Location: Bengaluru onsite/hybrid OR India-eligible remote (same as RISE).
  - Internship AND full-time both accepted (unlike RISE, which is intern-only).
  - Aggregators, WhatsApp/DM-only apply, blacklisted spam companies: reject.
"""
import quality_filter as qf

ROLE_TRACKS = ("founders_office", "ai_automation", "gtm")

SENIOR_TERMS = (
    "senior", "sr.", "staff", "principal", "director", "vp ", "vice president",
    "head of", "lead ", "manager", "10+ years", "8+ years", "7+ years",
    "6+ years", "5+ years", "minimum 5 years", "minimum 4 years", "3-5 years",
)

AI_KEYWORDS = (
    "artificial intelligence", "machine learning", " ml ", "llm", "genai",
    "generative ai", "gpt", "foundation model", "ai agent", "ai-native",
    "ai native", "ai product", "ai platform", "ai startup", "deep learning",
    "nlp", "computer vision", "copilot", "ai-powered", "ai powered", "agentic",
    " ai ", " ai,", " ai.", " ai)", "(ai",
)


def _norm(s):
    return (s or "").lower().strip()


def classify_ai_relevance(company, text, llm_ai_relevance=None):
    """Return 'strong' | 'moderate' | 'none'. Trusts the LLM judgment when
    given (it can read context a keyword list can't); falls back to a keyword
    heuristic over the company name + post text otherwise."""
    if llm_ai_relevance in ("strong", "moderate", "none"):
        return llm_ai_relevance
    blob = f" {_norm(company)} {_norm(text)} "
    hits = sum(1 for kw in AI_KEYWORDS if kw in blob)
    if hits >= 2:
        return "moderate"
    return "none"


def is_senior_role(role, experience_text=""):
    blob = f"{_norm(role)} {_norm(experience_text)}"
    return any(t in blob for t in SENIOR_TERMS)


def evaluate_founders_post(analysis: dict, post: dict) -> dict:
    """Final deterministic gate for the Founder's Office/AI Automation/GTM feed.

    Mirrors quality_filter.evaluate_post's structure and reuses its primitives,
    but swaps the RISE-specific unpaid-tech rule for role-track + AI-relevance
    + seniority checks that match Daksh's personal targeting strategy.
    """
    text = (post.get("text") or post.get("post_text") or "")
    author_name = post.get("authorName") or post.get("author_name") or ""
    author_headline = post.get("authorHeadline") or post.get("author_headline") or ""

    roles = analysis.get("roles") or ([analysis.get("role")] if analysis.get("role") else [])
    if isinstance(roles, str):
        roles = [roles]
    roles = [r for r in roles if r]
    primary_role = roles[0] if roles else (analysis.get("role") or "")

    location = analysis.get("location") or post.get("location") or ""
    work_mode = analysis.get("type") or post.get("type") or ""
    email = analysis.get("contact_email") or post.get("contact_email") or ""
    apply_link = analysis.get("apply_link") or post.get("apply_link") or ""
    company = _norm(analysis.get("company") or post.get("company") or "")

    result = {
        "accept": False, "reason": "", "score": 0, "apply_method": "none",
        "resolved_mode": "other", "role_track": "", "ai_relevance": "none",
    }

    # 1) Aggregator / reposter — same rule as RISE.
    is_agg, agg_reason = qf.is_aggregator_post(author_name, author_headline, text, roles)
    if analysis.get("is_aggregator_repost") is True:
        is_agg, agg_reason = True, "LLM flagged aggregator repost"
    if is_agg:
        result["reason"] = agg_reason
        return result

    # 1b) Blacklisted spam company.
    blob = " ".join([company, _norm(email), _norm(apply_link), _norm(author_name), _norm(author_headline)])
    if any(bl in blob for bl in qf.COMPANY_BLACKLIST):
        result["reason"] = "blacklisted spam company"
        return result

    # 2) Apply method — drop WhatsApp / DM / none.
    method = qf.classify_apply_method(text, email, apply_link)
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

    # 3) Location gate — Bengaluru onsite/hybrid OR India-eligible remote.
    accept_loc, mode, loc_reason = qf.location_decision(location, work_mode, text)
    result["resolved_mode"] = mode
    if not accept_loc:
        result["reason"] = loc_reason
        return result

    # 4) Role track must be Founder's Office / AI Automation / GTM.
    role_track = _norm(analysis.get("role_track"))
    if role_track not in ROLE_TRACKS:
        result["reason"] = f"role track mismatch ({role_track or 'unclear'})"
        return result
    result["role_track"] = role_track

    # 5) Seniority — entry-level / internship / associate only.
    if is_senior_role(primary_role, analysis.get("experience") or ""):
        result["reason"] = f"senior-level role ({primary_role})"
        return result

    # 6) AI-relevance — SOFT signal only (2026-07-22 policy update: Daksh said
    # AI-focus is preferred but not required, as long as the ROLE TRACK still
    # matches Founder's Office/AI Automation/GTM — a non-AI-company Founder's
    # Office internship is still on-target). Recorded for visibility/scoring,
    # never rejects on its own.
    ai_rel = classify_ai_relevance(company, text, _norm(analysis.get("ai_relevance")) or None)
    result["ai_relevance"] = ai_rel

    # 7) LLM legitimacy / genuineness guard — same as RISE.
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

    # Passed every gate — score for ranking.
    score = 40
    if company and company != "unknown":
        score += 15
    if method == "ats":
        score += 25
    elif method == "company_email":
        score += 18
    elif method == "form":
        score += 10
    elif method == "personal_email":
        score += 4
    if ai_rel == "strong":
        score += 10
    if mode == "bengaluru":
        score += 4
    result["score"] = min(100, score)
    result["accept"] = True
    return result
