"""
scrape_founders_roles.py
-------------------------
On-demand scraper for Daksh's PERSONAL job search feed: Founder's Office /
AI Automation / GTM Engineer roles at AI-focused startups, Bengaluru or
India-eligible remote, internship OR early full-time.

Separate from scrape_linkedin_posts.py (the RISE public-internship pipeline):
different queries, different LLM judgment (role-track + AI-relevance +
seniority), different output sheet. Reuses the harvestapi actor plumbing and
the aggregator/time pre-filter helpers since the anti-spam mechanics are the
same regardless of feed.

Output: .tmp/founders_roles_clean.json
"""
import os
import sys
import json
import re
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(__file__))
import scrape_linkedin_posts as S
import founders_llm_analyzer as FL
import quality_filter as qf

TMP_DIR = ".tmp"
CLEAN_OUTPUT = os.path.join(TMP_DIR, "founders_roles_clean.json")

MAX_POSTS_PER_QUERY = 15
POSTED_LIMIT = os.getenv("FOUNDERS_POSTED_LIMIT", "week")

BENGALURU_QUERIES = [
    "founder's office intern bangalore ai startup",
    "founder's office associate bangalore ai",
    "chief of staff intern bangalore startup",
    "ai automation engineer bangalore",
    "ai automation intern bangalore",
    "gtm engineer bangalore ai startup",
    "growth engineer bangalore ai",
]
REMOTE_QUERIES = [
    "founder's office intern remote india ai startup",
    "ai automation engineer remote india",
    "gtm engineer remote india ai",
    "growth engineer remote india ai startup",
    "chief of staff remote india ai startup",
]


def _prefilter(posts):
    """Light pre-cut before the LLM: dedup + aggregator + obvious story posts.
    Deliberately looser than RISE's pre-filter (no hard 4-day cutoff) since
    Founder's Office / GTM full-time postings stay open longer than intern posts."""
    seen = set()
    out = []
    story_kw = ("my journey", "excited to announce", "officially a",
                "i am looking for", "i'm looking for", "open to work")
    for p in posts:
        text = p.get("text") or ""
        if not text:
            continue
        norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text[:300])).lower().strip()
        key = p.get("url") or norm[:150]
        if key in seen:
            continue
        seen.add(key)
        if any(kw in norm for kw in story_kw):
            continue
        is_agg, _ = qf.is_aggregator_post(p.get("authorName", ""), p.get("authorHeadline", ""), text)
        if is_agg:
            continue
        out.append(p)
    return out


def main():
    os.makedirs(TMP_DIR, exist_ok=True)
    FL.configure_llm()
    print(f"LLM: {FL.PROVIDER} ({FL.MODEL})")
    if FL.PROVIDER == "none":
        print("No LLM configured — aborting (this feed needs LLM judgment, no regex fallback).")
        return []

    queries = BENGALURU_QUERIES + REMOTE_QUERIES
    print(f"Running {len(queries)} queries (postedLimit={POSTED_LIMIT}, max {MAX_POSTS_PER_QUERY}/query)...")

    all_raw = []
    for q in queries:
        run_input = {
            "searchQueries": [q],
            "maxPosts": MAX_POSTS_PER_QUERY,
            "postedLimit": POSTED_LIMIT,
            "sortBy": "date",
        }
        try:
            items = S.run_apify_actor(S.PRIMARY_ACTOR, run_input)
            norm = S._normalize_actor_items(S.PRIMARY_ACTOR, items) if items else []
        except Exception as e:
            print(f"   query failed '{q}': {e}")
            norm = []
        print(f"   '{q}' -> {len(norm)} raw posts")
        all_raw.extend(norm)

    print(f"\nTotal raw: {len(all_raw)}")
    try:
        with open(os.path.join(TMP_DIR, "founders_raw.json"), "w", encoding="utf-8") as _rf:
            json.dump(all_raw, _rf, ensure_ascii=False)
    except Exception as _e:
        print(f"   (raw dump failed: {_e})")
    prefiltered = _prefilter(all_raw)
    print(f"After pre-filter: {len(prefiltered)}")

    results = FL.batch_analyze_posts(prefiltered)
    print(f"\nVerified: {len(results)}")

    seen_cr = set()
    clean = []
    for post in results:
        company = post.get("company") or "Unknown"
        role = post.get("role") or "Role"
        cr = f"{S._normalize_company(company)}:{S._std_role_key(role)}"
        if cr in seen_cr:
            continue
        seen_cr.add(cr)

        ts = post.get("postedAtTimestamp")
        iso = post.get("postedAtISO") or ""
        hrs = S.parse_posted_time(iso or str(post.get("postedTime") or ""), ts)
        posted_date = (datetime.now() - timedelta(hours=hrs)).strftime("%Y-%m-%d") if hrs is not None else ""

        clean.append({
            "title": role, "role": role, "company": company,
            "hiringOrganization": company,
            "type": post.get("type") or "", "timing": post.get("timing") or "",
            "description": post.get("formatted_description") or (post.get("text") or "")[:1500],
            "stipend": post.get("stipend") or "", "duration": post.get("duration") or "",
            "experience": post.get("experience") or "", "location": post.get("location") or "",
            "deadline": post.get("deadline") or "",
            "tags": post.get("tags") or [],
            "contact_email": post.get("contact_email") or "",
            "apply_link": post.get("apply_link") or "",
            "author_name": post.get("authorName") or "",
            "url": post.get("url") or "",
            "role_track": post.get("role_track") or "",
            "ai_relevance": post.get("ai_relevance") or "",
            "posted_date": posted_date,
        })

    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(clean)} verified roles -> {CLEAN_OUTPUT}")
    return clean


if __name__ == "__main__":
    main()
