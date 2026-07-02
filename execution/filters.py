"""
filters.py
----------
Canonical, pure, dependency-free implementations of the deterministic filters
that decide whether a scraped post is a real, India-eligible internship.

These rules also live (inline, for speed) inside the scraping/LLM hot path in
`scrape_linkedin_posts.py` and `llm_post_analyzer.py`. This module is the
*reference* definition: it has no heavy imports, so it can be unit-tested and
measured by the eval harness (`execution/eval/eval_filters.py`) without spinning
up Apify, Google, or an LLM.

Every function is a pure predicate: text in, bool out. No I/O, no globals.
"""

from __future__ import annotations

import re

# ── Pattern banks ─────────────────────────────────────────────────────────
# Pay-to-work and work-from-home "earn daily" scams that flood LinkedIn.
SCAM_PATTERNS = [
    "registration fee", "reg fee", "registration charges",
    "training fee", "training charges", "training cost",
    "security deposit", "caution money", "certification fee",
    "pay to join", "pay to work", "investment required", "investment needed",
    "typing job", "data entry job", "form filling", "copy paste",
    "earn daily", "earn per day", "easy money", "work from home earn",
    "100 genuine", "100% genuine", "guaranteed income", "guaranteed placement",
    "whatsapp to register", "whatsapp registration",
    "simple typing", "home based typing", "no investment",
]

# First-person / celebration posts that are not job openings.
STORY_PATTERNS = [
    "my journey", "wrapped up my time", "excited to announce", "officially a",
    "vibecoding", "from learning to earning", "i am looking for",
    "i'm looking for", "seeking a", "seeking an", "open to work",
    "happy to share", "thrilled to share", "completed my internship",
    "grateful to", "proud to share",
]

# Signals that a post is actually recruiting for something.
HIRING_PATTERNS = [
    "hiring", "looking for", "apply", "opportunity", "openings", "opening",
    "interns required", "join our team", "we are expanding", "internship alert",
    "recruiting", "vacancy", "we're hiring", "now hiring",
]

# International spammers with no India relevance.
COMPANY_BLACKLIST = ["gao group", "gaotek", "gao tek"]

INDIA_CITIES = [
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi",
    "gurgaon", "gurugram", "noida", "hyderabad", "chennai", "pune",
    "kolkata", "ahmedabad", "jaipur", "lucknow", "chandigarh", "indore",
    "kochi", "coimbatore", "nagpur", "bhopal", "visakhapatnam",
    "thiruvananthapuram", "surat", "vadodara", "mysore", "mangalore",
    "pan india", "wfh", "work from home",
]

OUTSIDE_INDICATORS = [
    "usa", "uk", "london", "new york", "san francisco", "los angeles",
    "dubai", "uae", "australia", "canada", "germany", "singapore",
    "hong kong", "europe", "united states", "united kingdom", "korea",
    "japan", "china", "malaysia", "netherlands", "france", "italy",
    "toronto", "sydney", "berlin", "amsterdam", "paris", "seoul",
    "riyadh", "kuwait", "qatar", "bahrain", "oman",
]

INDIA_TEXT_KEYWORDS = [
    "india", "bangalore", "bengaluru", "mumbai", "delhi",
    "hyderabad", "pune", "noida", "gurgaon", "chennai",
    "kolkata", "ahmedabad", "jaipur", "pan india",
    "indian students", "for india", "in india", "indian candidates",
]


def normalize(text: str) -> str:
    """Lowercase and strip punctuation the same way the scraper pre-filter does,
    so predicates here match the production hot path."""
    t = re.sub(r"[^\w\s]", "", (text or "")[:300]).lower()
    return re.sub(r"\s+", " ", t).strip()[:150]


def is_scam(text: str) -> bool:
    """True if the post trips any pay-to-work / earn-daily scam pattern."""
    norm = normalize(text)
    return any(p in norm for p in SCAM_PATTERNS)


def is_personal_story(text: str) -> bool:
    """True if the post is a personal update/celebration, not an opening."""
    norm = normalize(text)
    return any(p in norm for p in STORY_PATTERNS)


def has_hiring_intent(text: str) -> bool:
    """True if the post shows any sign of actively recruiting."""
    norm = normalize(text)
    return any(p in norm for p in HIRING_PATTERNS) or "intern" in norm


def is_blacklisted_company(name: str) -> bool:
    """True for known international spam companies."""
    n = (name or "").lower().strip()
    return any(bl in n for bl in COMPANY_BLACKLIST)


def is_india_eligible(location: str, text: str = "") -> bool:
    """Decide whether an internship is open to candidates in India.

    Rules (mirrors the post-LLM logic in the pipeline):
      - Reject if the location names a place outside India and never mentions India.
      - Accept if the location names an Indian city / "pan india" / WFH.
      - "Remote"-only or unknown location: accept only if the post *text*
        gives India context (a city, "in India", "Indian candidates", ...).
    """
    loc = (location or "").lower()
    body = (text or "").lower()

    is_outside = any(kw in loc for kw in OUTSIDE_INDICATORS)
    if is_outside and "india" not in loc:
        return False

    if any(kw in loc for kw in INDIA_CITIES):
        return True

    # Remote-only or unknown → require India context in the body.
    if "remote" in loc or not loc.strip():
        return any(kw in body for kw in INDIA_TEXT_KEYWORDS)

    # A named non-India, non-outside location with no India context.
    return any(kw in body for kw in INDIA_TEXT_KEYWORDS)


def classify(text: str, location: str = "", company: str = "") -> tuple[bool, str]:
    """Full deterministic verdict for one post.

    Returns (keep, reason). `keep=False` means the post should be dropped and
    `reason` says why (used by the eval harness for a confusion breakdown).
    """
    if is_blacklisted_company(company):
        return False, "blacklisted_company"
    if is_scam(text):
        return False, "scam"
    if is_personal_story(text):
        return False, "personal_story"
    if not has_hiring_intent(text):
        return False, "no_hiring_intent"
    if not is_india_eligible(location, text):
        return False, "not_india_eligible"
    return True, "ok"
