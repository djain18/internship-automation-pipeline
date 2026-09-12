"""
role_taxonomy.py
----------------
Single source of truth for "what kind of role is this?" across the whole
pipeline AND the website API.

Before this module there were THREE divergent role mappers that disagreed:
  - api/sheets.py::_infer_cluster          (display cluster on the site)
  - publish_to_sheets.py::standardize_role_for_dedup  (dedup key)
  - scrape_linkedin_posts.py::_std_role_key           (cross-query dedup)
An "AI Automation Intern" showed as cluster `AI Automation` on the site but
deduped under key `data`, so it silently collided with an unrelated data role
at the same company. All three now delegate here.

Two levels, deliberately distinct:

  track  — a QUOTA bucket (12 of them). Drives the nightly per-role cap, the
           search-query plan, and dedup. Coarse on purpose: Finance, HR and
           Legal share one track because they compete for the same slot.
  cluster— the DISPLAY label shown on the site and stored in subscribers'
           saved Firestore `roles`. Finer-grained, and every label that
           _infer_cluster used to emit is still emitted, so existing sheet
           rows, front-end filter chips, and saved preferences keep working.

One ordered rule table produces both, so they can never drift apart again.

Why the ordering matters (same reasoning as the old _infer_cluster comment):
specific, fast-growing 2026 role families must resolve BEFORE the broad
buckets that would otherwise swallow them — `forward_deployed` and
`product_engineering` before `software`, `ai_automation` before `data_ml`.

Dependency-free (stdlib `re` only) on purpose: this file is mounted into
Modal's lightweight `api_image`, which installs none of the pipeline's deps.
"""

import re

# ─────────────────────────────────────────────────────────────────────────────
# City scopes for the search-query plan
# ─────────────────────────────────────────────────────────────────────────────
# Query count is the real budget here: every query is an Apify actor call, and
# 5 workers x ~2min each is what sets the nightly runtime. A naive
# tracks x terms x 12-cities cross-product came out at 238 queries (~2x today's
# runtime), so each scope is sized deliberately and the wide scope ROTATES.

# Full internship-volume ranking (mirrors ACCEPTED_CITY_TERMS in
# quality_filter.py). Tracks on this scope sample WIDE_SAMPLE of these per
# night, rotating daily, so all 12 are covered across a week without paying for
# 12 queries per term every single run.
ALL_CITIES = (
    "bangalore", "mumbai", "delhi", "gurgaon", "noida", "pune",
    "hyderabad", "chennai", "jaipur", "ahmedabad", "kolkata", "indore",
)
WIDE_SAMPLE = 6

# Startup-dense cities. Founder's-office / forward-deployed / AI-automation
# roles essentially only exist at funded startups, and the 2026-08-22 run
# confirmed the other cities return 0 for them. These tracks have the most
# query TERMS, so they get the fewest cities — most of their real supply is
# remote anyway, and the remote-India pass covers that.
STARTUP_CITIES = ("bangalore", "delhi", "mumbai")

# Tracks whose supply already exceeds their quota many times over. Marketing
# alone returned 94 of 219 raw posts last run off a single query; querying it
# wide just bills Apify for posts the quota will cap away.
CORE_CITIES = ("bangalore", "mumbai", "delhi", "hyderabad")

REMOTE_SUFFIX = "remote india"

_WIDE, _STARTUP, _CORE = "wide", "startup", "core"

# ─────────────────────────────────────────────────────────────────────────────
# Tracks
# ─────────────────────────────────────────────────────────────────────────────
# `scarce` tracks get a 7-day scrape window instead of 24h and a higher
# per-query post cap. They post rarely enough that a 24h window returns nothing
# — which is exactly why the sheet had zero of them. Dedup already prevents
# re-publishing, so a wider window costs nothing but slightly older posts.
TRACKS = (
    {"key": "founders_office",    "label": "Founder's Office",   "scarce": True,  "cities": _STARTUP},
    {"key": "forward_deployed",   "label": "Forward Deployed",   "scarce": True,  "cities": _STARTUP},
    {"key": "ai_automation",      "label": "AI Automation",      "scarce": True,  "cities": _STARTUP},
    {"key": "product_engineering","label": "Product Engineering","scarce": True,  "cities": _STARTUP},
    {"key": "software",           "label": "Software",           "scarce": False, "cities": _WIDE},
    {"key": "data_ml",            "label": "Data/AI",            "scarce": False, "cities": _WIDE},
    {"key": "product",            "label": "Product",            "scarce": False, "cities": _WIDE},
    {"key": "design",             "label": "Design",             "scarce": False, "cities": _CORE},
    {"key": "business_ops",       "label": "Business Ops",       "scarce": True,  "cities": _STARTUP},
    {"key": "sales_bd",           "label": "Business Dev",       "scarce": False, "cities": _WIDE},
    {"key": "marketing_content",  "label": "Marketing",          "scarce": False, "cities": _CORE},
    {"key": "finance_hr_legal",   "label": "Finance",            "scarce": False, "cities": _CORE},
)

TRACK_KEYS = tuple(t["key"] for t in TRACKS)
SCARCE_TRACKS = frozenset(t["key"] for t in TRACKS if t["scarce"])
_TRACK_BY_KEY = {t["key"]: t for t in TRACKS}

# What we type into LinkedIn search, per track. Kept separate from the
# classification vocab below: a good search phrase ("hiring founder's office")
# is not the same thing as a good title matcher.
QUERY_TERMS = {
    "founders_office": [
        "founders office intern",
        "founder's associate chief of staff intern",
        "business generalist entrepreneur in residence intern",
    ],
    "forward_deployed": [
        "forward deployed engineer intern",
        "solutions engineer implementation engineer intern",
    ],
    "ai_automation": [
        "ai automation intern",
        "ai agent agentic llm engineer intern",
        "generative ai genai prompt engineer intern",
        "workflow automation n8n zapier intern",
    ],
    "product_engineering": [
        "product engineer intern",
        "growth engineer gtm engineer intern",
        "founding engineer intern",
    ],
    "software": [
        "software full stack backend frontend developer intern",
        "android ios mobile devops cloud qa engineer intern",
    ],
    "data_ml": [
        "data science machine learning intern",
        "data analyst business analyst analytics intern",
    ],
    "product": [
        "product management associate product manager intern",
    ],
    "design": [
        "product design ui ux graphic design intern",
    ],
    "business_ops": [
        "business operations strategy intern",
        "revenue operations business analyst consulting intern",
    ],
    "sales_bd": [
        "business development sales partnerships intern",
    ],
    "marketing_content": [
        "digital marketing seo social media content writing intern",
    ],
    "finance_hr_legal": [
        "finance accounting fpa intern",
        "human resources talent acquisition legal compliance intern",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Classification rules — ORDERED, most specific first.
# Each rule is (substring terms, extra word-boundary regex or None, track, cluster).
# ─────────────────────────────────────────────────────────────────────────────
# "ai"/"ml"/"ui"/"ux" need word-boundary matching, not bare substring — "ai"
# alone falsely matches inside "fundraising", "training", "email"; "ui" falsely
# matches inside "acquisition", "equity", "recruitment". (Carried over verbatim
# from api/sheets.py, where Internshala's raw category titles surfaced this.)
_AI_ML_WORD_RE = re.compile(r"\b(ai|ml)\b")
_UI_UX_WORD_RE = re.compile(r"\b(ui|ux)\b")

_RULES = (
    (("founder's office", "founders office", "founder office", "founder's associate",
      "founders associate", "chief of staff", "business generalist",
      "entrepreneur in residence"), None, "founders_office", "Founder's Office"),

    (("forward deployed", "deployment engineer", "implementation engineer",
      "solutions engineer", "solutions architect", "technical account"),
     None, "forward_deployed", "Forward Deployed"),

    (("ai automation", "automation engineer", "workflow automation", "ai agent",
      "agentic", "ai ops", "llm engineer", "genai", "generative ai",
      "prompt engineer", "ai engineer", "automation intern"),
     None, "ai_automation", "AI Automation"),

    (("product engineer", "growth engineer", "gtm engineer", "founding engineer"),
     None, "product_engineering", "Product Engineering"),

    (("software", "sde", "developer", "frontend", "backend", "full stack",
      "fullstack", "web", "ios", "android", "flutter", "mobile", "devops",
      "sdet", "qa engineer", "test engineer", "cybersecurity", "embedded"),
     None, "software", "Software"),

    (("data", "machine learning", "analytics", "scientist"),
     _AI_ML_WORD_RE, "data_ml", "Data/AI"),

    (("product", " pm ", "apm"), None, "product", "Product"),

    # Marketing checked ahead of Design: a "Digital Marketing Intern" tagged
    # "Video Editing" (a social-media-content skill, not a design role) was
    # being caught by Design's bare "video" keyword first.
    (("marketing", "seo", "social media", "growth", "performance"),
     None, "marketing_content", "Marketing"),

    (("design", "graphic", "video", "motion", "figma"),
     _UI_UX_WORD_RE, "design", "Design"),

    (("finance", "audit", "accounting", "equity", "markets", "fp&a", "fpa"),
     None, "finance_hr_legal", "Finance"),

    (("sales", "business development", " bd ", "bdr", "sdr", "partnerships"),
     None, "sales_bd", "Business Dev"),

    ((" hr ", "human resources", "talent", "recruit", "people ops"),
     None, "finance_hr_legal", "HR"),

    (("content", "writing", "copywriting", "editorial"),
     None, "marketing_content", "Content"),

    (("legal", "compliance", "contracts", " law "),
     None, "finance_hr_legal", "Legal"),

    (("business operations", "biz ops", "bizops", "revenue operations",
      "revops", "strategy", "consulting", "operations"),
     None, "business_ops", "Business Ops"),
)

# Fallback when nothing matches — preserves _infer_cluster's historical default.
_DEFAULT_TRACK, _DEFAULT_CLUSTER = "business_ops", "Operations"

# Every cluster label this module can emit, in display order. The front end
# derives its filter chips from the live data, but Dashboard.jsx uses this
# order (via CLUSTER_ICON's key order) to sort them.
CLUSTER_LABELS = tuple(
    dict.fromkeys([r[3] for r in _RULES] + [_DEFAULT_CLUSTER])
)

# Reverse map so an already-classified cluster label (e.g. read back off the
# sheet, or a subscriber's saved preference) resolves to its quota track.
_TRACK_BY_CLUSTER = {r[3]: r[2] for r in _RULES}
_TRACK_BY_CLUSTER[_DEFAULT_CLUSTER] = _DEFAULT_TRACK


def _classify(title, tags=()):
    """Return (track_key, cluster_label) for a role title + optional tags."""
    if isinstance(tags, str):
        tags = [tags]
    text = " ".join([str(title or "")] + [str(t) for t in (tags or [])]).lower()
    # Pad so " pm " / " ai " style boundary terms can match at the edges.
    padded = f" {text} "
    for terms, word_re, track, cluster in _RULES:
        if any(t in padded for t in terms):
            return track, cluster
        if word_re is not None and word_re.search(text):
            return track, cluster
    return _DEFAULT_TRACK, _DEFAULT_CLUSTER


def infer_track(title, tags=()):
    """Quota/dedup bucket for a role. One of TRACK_KEYS."""
    return _classify(title, tags)[0]


def infer_cluster(title, tags=()):
    """Display label for a role, as shown on the site. One of CLUSTER_LABELS."""
    return _classify(title, tags)[1]


def track_label(key):
    """Primary display label for a track key."""
    t = _TRACK_BY_KEY.get(key)
    return t["label"] if t else _DEFAULT_CLUSTER


def track_for_cluster(label):
    """Map a display cluster label back to its quota track.

    Lets the digest cap and any consumer that only has a classified listing
    (not a raw title) reuse the same buckets.
    """
    return _TRACK_BY_CLUSTER.get(label) or infer_track(label)


def is_scarce(track_key):
    return track_key in SCARCE_TRACKS


# ═════════════════════════════════════════════════════════════════════════════
# Search-query plan
# ═════════════════════════════════════════════════════════════════════════════
def _cities_for(scope, rotation=0):
    """Resolve a track's city scope, rotating the wide scope by `rotation`.

    Rotation is what lets abundant tracks keep nationwide reach without paying
    for all 12 cities every night: run N covers a 6-city window, run N+1 covers
    the next, and a week covers everything.
    """
    if scope == _STARTUP:
        return STARTUP_CITIES
    if scope == _CORE:
        return CORE_CITIES
    n = len(ALL_CITIES)
    start = rotation % n
    return tuple(ALL_CITIES[(start + i) % n] for i in range(WIDE_SAMPLE))


def query_plan(rotation=0):
    """Build the nightly LinkedIn search plan.

    Returns a list of dicts: {"query", "track", "scarce"}.

    Each track is crossed with its own city scope plus one remote-India pass.
    Deliberately weighted toward the scarce tracks: they get the most query
    terms because they are what the sheet was missing entirely, while marketing
    drops from 13 queries to 5 because one query already oversupplies it.

    Apify bills per RESULT, not per query, so a narrow track that returns
    little costs almost nothing beyond its latency.
    """
    plan = []
    for track in TRACKS:
        cities = _cities_for(track["cities"], rotation)
        for terms in QUERY_TERMS[track["key"]]:
            for city in cities:
                plan.append({"query": f"{terms} {city}",
                             "track": track["key"], "scarce": track["scarce"]})
            plan.append({"query": f"{terms} {REMOTE_SUFFIX}",
                         "track": track["key"], "scarce": track["scarce"]})
    return plan


# ═════════════════════════════════════════════════════════════════════════════
# The nightly balance
# ═════════════════════════════════════════════════════════════════════════════
DEFAULT_QUOTA = 5
DEFAULT_TOTAL_TARGET = 45
# Hard ceiling a track can reach even after redistribution. Without it, an
# unbounded round-robin hands the entire surplus back to whichever track is
# oversupplied — on the 2026-08-22 data that put marketing straight back to 26
# of 29, i.e. exactly the bug this function exists to fix.
DEFAULT_MAX_PER_TRACK = DEFAULT_QUOTA * 2


def balance(posts, quota=DEFAULT_QUOTA, total_target=DEFAULT_TOTAL_TARGET,
            max_per_track=DEFAULT_MAX_PER_TRACK,
            title_key="title", tags_key="tags", score_key="quality_score"):
    """Cap each role track at `quota`, then redistribute unused capacity.

    This runs AFTER the quality gate, never before: quality_filter decides what
    is publishable, `balance` only decides which of the survivors to publish.
    Nothing is ever padded — if genuine supply is short we return fewer, which
    keeps run_pipeline.py's quality-first contract intact.

    Ranking within a track uses the genuineness score quality_filter.
    evaluate_post already computed, so there is no second notion of "good".

    `quota` is the fair share every track gets first; `max_per_track` is the
    ceiling no track may pass even when it inherits other tracks' unused slots.

    Returns a new list; input is not mutated.
    """
    if not posts:
        return []

    buckets = {}
    for p in posts:
        track = infer_track(p.get(title_key) or p.get("role") or "",
                            p.get(tags_key) or ())
        buckets.setdefault(track, []).append(p)

    def rank(p):
        try:
            return -int(p.get(score_key) or 0)
        except (TypeError, ValueError):
            return 0

    for track in buckets:
        buckets[track].sort(key=rank)

    picked, leftovers, taken = [], {}, {}
    known = set(TRACK_KEYS)
    # Any track key outside TRACK_KEYS can't happen (infer_track is closed over
    # them), but stay defensive rather than silently dropping rows.
    order = list(TRACK_KEYS) + [t for t in buckets if t not in known]
    for track in order:
        queued = buckets.get(track, [])
        picked.extend(queued[:quota])
        taken[track] = min(len(queued), quota)
        if len(queued) > quota:
            leftovers[track] = queued[quota:]

    # Redistribute: tracks that came up dry release their unused slots, and the
    # remaining capacity goes round-robin to tracks that still have queued
    # posts. Round-robin (not "biggest bucket first") plus the per-track ceiling
    # is what stops marketing from reclaiming the entire surplus on its own.
    if total_target and len(picked) < total_target and leftovers:
        room = total_target - len(picked)
        rota = [t for t in order if leftovers.get(t)]
        while room > 0 and rota:
            progressed = False
            for track in list(rota):
                if room <= 0:
                    break
                queue = leftovers.get(track)
                if not queue or taken[track] >= max_per_track:
                    rota.remove(track)
                    continue
                picked.append(queue.pop(0))
                taken[track] += 1
                room -= 1
                progressed = True
            if not progressed:
                break

    return picked


def mix(posts, title_key="title", tags_key="tags"):
    """{cluster_label: count} for a list of posts — for logging and tests."""
    out = {}
    for p in posts:
        label = infer_cluster(p.get(title_key) or p.get("role") or "",
                              p.get(tags_key) or ())
        out[label] = out.get(label, 0) + 1
    return out
