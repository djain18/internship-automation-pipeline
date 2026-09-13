"""Free evidence read from a company's own website.

The strongest free signal about what a small company is actually doing is the
company's own about, product, careers, blog, or changelog page. This module
fetches a small number of those pages, respecting robots.txt, and turns them
into evidence entries carrying a URL and an access date. Nothing here infers,
summarizes beyond quoting, or invents: an entry is a real sentence that really
appears on a real page.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from models import Record, canonical_url, clean_text

# 2026-09-13: reordered operational-first. The homepage/about/product pages
# are always marketing copy, which problem_research.py's Kimi instruction
# now explicitly refuses to treat as evidence of an internal problem
# (marketing copy describes what a company sells, not how it operates) --
# so pages that are actually about how the company operates internally
# (careers, jobs, blog, engineering) are tried first, homepage last.
CANDIDATE_PATHS = (
    "/careers",
    "/jobs",
    "/blog",
    "/changelog",
    "/engineering",
    "/about",
    "/about-us",
    "/company",
    "",
)
OPERATIONAL_PATHS = {"/careers", "/jobs", "/blog", "/changelog", "/engineering"}

# Pages that describe what the company does read like this. A page that matches
# nothing is almost certainly a cookie banner or a login wall, and quoting it
# would put noise in the brief.
SIGNAL_TERMS = (
    "we build",
    "we help",
    "we are building",
    "our platform",
    "our product",
    "our mission",
    "customers",
    "founded",
    "team",
    "hiring",
    "launch",
)

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LINKEDIN_PROFILE_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/[\w-]+"
)


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _robots(session: requests.Session, base: str, timeout: int) -> RobotFileParser:
    parser = RobotFileParser()
    parser.set_url(urljoin(base, "/robots.txt"))
    try:
        response = session.get(urljoin(base, "/robots.txt"), timeout=timeout)
        if response.status_code >= 400:
            # No robots file is an allow, per the standard. A server error is
            # not, so treat anything else as closed.
            parser.parse([] if response.status_code == 404 else ["User-agent: *", "Disallow: /"])
        else:
            parser.parse(response.text.splitlines())
    except requests.RequestException:
        parser.parse(["User-agent: *", "Disallow: /"])
    return parser


def _sentences(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # Split on line breaks before sentence punctuation: a job page's bullets
    # carry no full stops, so collapsing whitespace first fused a header onto
    # its first bullet ("What you will do * Run outbound every day.").
    parts = [
        clean_text(part)
        for line in soup.get_text("\n").splitlines()
        for part in re.split(r"(?<=[.!?])\s+", clean_text(line).lstrip("*•-– ").strip())
    ]
    return [part for part in parts if 40 <= len(part) <= 300]


def fetch_site_evidence(
    company_url: str,
    user_agent: str = "InternshipResearch/0.1",
    timeout: int = 10,
    max_pages: int = 3,
) -> tuple[list[Record], list[str], list[str], str]:
    """Return (evidence, published_emails, published_linkedin_urls, status) for one company website.

    Never raises: research runs inside the pipeline and a slow or hostile site
    must not take the run down with it.
    """

    base = canonical_url(company_url)
    if not base.startswith("http"):
        return [], [], [], "no_company_url"
    origin = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}"
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    robots = _robots(session, origin, timeout)
    access_date = _utc_date()
    evidence: list[Record] = []
    emails: list[str] = []
    linkedin_urls: list[str] = []
    blocked = 0
    for path in CANDIDATE_PATHS:
        if len(evidence) >= max_pages:
            break
        url = urljoin(origin + "/", path.lstrip("/"))
        if not robots.can_fetch(user_agent, url):
            blocked += 1
            continue
        try:
            response = session.get(url, timeout=timeout)
        except requests.RequestException:
            continue
        if response.status_code >= 400 or "html" not in response.headers.get(
            "Content-Type", ""
        ):
            continue
        emails.extend(
            match.rstrip(".,;:)")
            for match in EMAIL_PATTERN.findall(response.text)
            # Tracking pixels and asset hashes look like addresses often enough
            # to be worth excluding by extension.
            if not match.casefold().endswith((".png", ".jpg", ".gif", ".svg", ".webp"))
        )
        # Extract LinkedIn profile URLs from company team/about pages
        linkedin_urls.extend(LINKEDIN_PROFILE_PATTERN.findall(response.text))
        # Tag by WHICH PAGE this came from, not by sentence content.
        # primary_responsibility() (its OWNERSHIP_VERBS: build, help, support,
        # run...) was built for structured job-listing sentences ("You will
        # own X") and, tried against real company_site.py fetches of
        # emergent.sh/lyzr.ai, matched cookie-banner boilerplate and the
        # company's own product tagline ("Build production-ready apps
        # through conversation") as "operational" -- worse than the plain
        # SIGNAL_TERMS match it was meant to replace, because ordinary
        # marketing copy uses these exact verbs too. Page origin (careers/
        # jobs/blog/changelog/engineering vs about/company/homepage) is a
        # far more reliable operational-vs-descriptive signal than any
        # sentence-level verb check on arbitrary webpage HTML.
        quoted = next(
            (
                line
                for line in _sentences(response.text)
                if any(term in line.casefold() for term in SIGNAL_TERMS)
            ),
            "",
        )
        if not quoted:
            continue
        basis = (
            "company_site_operational"
            if path in OPERATIONAL_PATHS
            else "company_site_descriptive"
        )
        evidence.append(
            {
                "url": canonical_url(response.url),
                "observation": quoted,
                "access_date": access_date,
                "confidence": "medium",
                "basis": basis,
            }
        )
    if evidence:
        return evidence, sorted(set(emails)), sorted(set(linkedin_urls)), "ok"
    if blocked:
        return [], sorted(set(emails)), sorted(set(linkedin_urls)), "robots_disallowed"
    return [], sorted(set(emails)), sorted(set(linkedin_urls)), "no_usable_page"


# Verbs a posting uses when it describes work someone will own. The sentence
# that carries one is the closest thing a listing has to a statement of the
# operational gap the company is hiring to close.
# Verb stems, not whole words: the regex below re-attaches inflections, so
# "own" also covers owns/owned/owning. Doubling verbs carry a second stem
# ("run" + "runn") because the doubled consonant is part of the inflected form.
#
# Widened 2026-09-13. The old list plus an exact `f"{verb} "` substring test
# matched a quotable responsibility sentence in only 3 of the 13 records that
# have ever reached a digest. Every miss was a verb the list did not carry or
# an inflection the space-suffix test could not see:
#   "Work directly with the founder across AI automation..."   (Nebula AI)
#   "Partner with founders on AI agent launches..."            (AgentNest)
#   "You'll work at the intersection of strategy, operations"  (Kplor)
#   "involved in ... and building things from the ground up"   (Auraaison)
# Those misses are what forced deterministic_research onto its tautological
# fallback observation ("X published or was listed for Y"), which is what every
# outreach prompt was then built on.
OWNERSHIP_VERBS = (
    "own", "manag", "build", "coordinat", "track", "run", "runn", "streamlin",
    "scal", "improv", "automat", "driv", "set up", "support", "work", "partner",
    "lead", "launch", "execut", "ship", "shipp", "handl", "creat", "research",
    "collaborat", "assist", "help", "analys", "analyz", "report", "prepar",
)

# stem + one inflection + a word boundary. The boundary is what keeps "run"
# from matching "runway" and "own" from matching "ownership" mid-word, which a
# bare `\w{0,3}` suffix would have let through.
_OWNERSHIP_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(verb).replace(r"\ ", r"\s+") for verb in OWNERSHIP_VERBS)
    + r")(?:e|es|ed|ing|s|en)?\b"
)


# Feed and aggregator boilerplate that sits in the same field as the real
# description. Quoting it produced "Ressl AI (W26) Train, eval and build
# autonomous agents ( 2 days ago) GTM..." in a real run.
FEED_NOISE = ("days ago", "day ago", "hours ago", "apply now", "posted on")


# Sentences that use an ownership verb but describe the ad, not the work.
# Widening OWNERSHIP_VERBS made these reachable: a real run picked "HR agencies
# - we're handling these hires in-house for now, so please don't spam us" as
# SuprSend's primary responsibility, which would then be quoted verbatim into
# the outreach prompt as "The listing states: ...".
PITCH_NOISE = (
    "hr agencies", "spam", "love to hear from you", "tag them", "share this",
    "know someone", "dm me", "drop your", "comment below", "send your resume",
    "send your cv", "stipend:", "ppo:", "ctc", "referral", "repost",
)

# Markers that a sentence is describing the role's own work. Preferred over a
# merely longer sentence, because the longest qualifying line is usually the
# closing pitch ("If you want exposure to what actually happens behind the
# scenes...") rather than the responsibility.
RESPONSIBILITY_MARKERS = (
    "you'll", "you will", "you’ll", "the intern", "as an intern", "role:",
    "responsibilit", "what you", "your day", "work directly", "partner with",
    "working directly", "assist the", "support the", "you would", "day-to-day",
    "day to day",
)


def primary_responsibility(description: str) -> str:
    """The listing's own words for what the role will do. Never paraphrased."""

    candidates = [
        line
        for line in _sentences(str(description or "").replace(chr(65533), " "))
        if _OWNERSHIP_PATTERN.search(line.casefold())
        and not any(noise in line.casefold() for noise in FEED_NOISE)
        and not any(noise in line.casefold() for noise in PITCH_NOISE)
        # Application-form questions ("What are the first two experiments you
        # would recommend?") use the same verbs but describe no work.
        and not line.rstrip().endswith("?")
    ]
    if not candidates:
        return ""
    # A sentence that names the role's own work beats a merely longer one. Only
    # when none does is length the best available signal, as before.
    described = [
        line
        for line in candidates
        if any(marker in line.casefold() for marker in RESPONSIBILITY_MARKERS)
    ]
    return max(described or candidates, key=len)

OFFICE_PATHS = ("", "/about", "/about-us", "/contact", "/contact-us", "/careers")

OFFICE_TERMS = (
    "office", "offices", "headquarter", "headquarters", "located",
    "based", "address", "work from", "onsite", "hybrid", "workplace",
)

CITY_TERMS = ("bengaluru", "bangalore")


def find_office_evidence(html_text: str, page_url: str) -> Record | None:
    """A quoted sentence placing an office in Bengaluru, or None.

    Both a city term and an office term must share one sentence, so "we serve
    customers in Bengaluru" does not qualify. Quote only, never inference.
    """

    for sentence in _sentences(str(html_text or "")):
        lowered = sentence.casefold()
        if any(city in lowered for city in CITY_TERMS) and any(
            term in lowered for term in OFFICE_TERMS
        ):
            return {
                "observation": sentence[:240],
                "url": canonical_url(page_url),
                "access_date": _utc_date(),
                "confidence": "medium",
                "basis": "company_site_office",
            }
    return None


# Phrases job pages and ATS boards print once a role stops taking applicants
# while still answering 200, which the HEAD-based link check cannot see.
CLOSED_LISTING_PHRASES = (
    "no longer accepting applications",
    "not accepting applications",
    "this position has been filled",
    "position has been filled",
    "this job is no longer available",
    "job is no longer available",
    "this job has expired",
    "job posting has expired",
    "no longer open",
    "applications are closed",
    "this role has been filled",
    "the job you are looking for",
)
_CLOSED_HOSTS_SKIPPED = ("linkedin.com", "lnkd.in")


def _skipped_host(host: str) -> bool:
    return any(host == skipped or host.endswith("." + skipped) for skipped in _CLOSED_HOSTS_SKIPPED)


def _page_text(html_text: str) -> str:
    """Visible page text with line breaks kept, so a bulleted job description
    still splits into its own sentences."""
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    lines = (clean_text(line) for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def read_public_page(
    url: str,
    user_agent: str = "InternshipResearch/0.1",
    timeout: int = 10,
    max_bytes: int = 400_000,
) -> str:
    """Visible text of one public page, or "". Robots-respecting, one GET,
    never raising, never LinkedIn (this pipeline may not open it)."""

    target = canonical_url(url)
    parts = urlsplit(target)
    if not target.startswith("http") or _skipped_host(parts.netloc.casefold()):
        return ""
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    try:
        robots = _robots(session, f"{parts.scheme}://{parts.netloc}", timeout)
        if not robots.can_fetch(user_agent, target):
            return ""
        response = session.get(target, timeout=timeout, stream=True)
        if response.status_code >= 400:
            return ""
        raw = response.raw.read(max_bytes, decode_content=True)
    except Exception:
        return ""
    # requests assumes ISO-8859-1 for text/html without a charset, which
    # mangled "Founder’s" on binary.so; job pages are UTF-8 in practice.
    declared = (response.headers.get("Content-Type") or "").casefold()
    encoding = response.encoding if "charset=" in declared else "utf-8"
    return _page_text(raw.decode(encoding or "utf-8", errors="replace"))


_ASHBY_JOB = re.compile(r"^https?://jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", re.I)
_GREENHOUSE_JOB = re.compile(r"^https?://(?:boards|job-boards)\.greenhouse\.io/([^/]+)/jobs/(\d+)", re.I)
_LEVER_JOB = re.compile(r"^https?://jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})", re.I)


def fetch_listing_text(url: str, timeout: int = 15) -> str:
    """The full job description behind an apply or source link, or "".

    The digest's listings often carry only a post or a title. The page the
    link opens holds the real description -- SuprSend's "map the ecosystem,
    get us listed where buyers look, track reply rates", Ressl AI's "do not use
    AI to write it" -- which is what a specific outreach needs and what a
    Firecrawl news search did not find (2026-09-13 comparison: generic
    hypotheses and a docs-site placeholder address). Ashby, Greenhouse and
    Lever render client-side, so their public posting APIs are read instead of
    the page; everything else is one robots-respecting GET. Free, no key.
    """

    target = canonical_url(url)
    try:
        if match := _ASHBY_JOB.match(target):
            board = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{match.group(1)}", timeout=timeout
            ).json()
            job = next((item for item in board.get("jobs") or [] if item.get("id") == match.group(2)), None)
            return str(job.get("descriptionPlain") or "") if job else ""
        if match := _GREENHOUSE_JOB.match(target):
            job = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{match.group(1)}/jobs/{match.group(2)}",
                timeout=timeout,
            ).json()
            return _page_text(html.unescape(str(job.get("content") or "")))
        if match := _LEVER_JOB.match(target):
            job = requests.get(
                f"https://api.lever.co/v0/postings/{match.group(1)}/{match.group(2)}", timeout=timeout
            ).json()
            return "\n".join(
                filter(None, [str(job.get("descriptionPlain") or ""), str(job.get("additionalPlain") or "")])
            )
    except Exception:
        return ""
    return read_public_page(target, timeout=timeout)


def closed_listing_signal(url: str, user_agent: str = "InternshipResearch/0.1", timeout: int = 10) -> str:
    """The exact closed-listing phrase a job page prints, or "". An empty
    result means "no closed signal seen", never "confirmed open"."""

    lowered = read_public_page(url, user_agent=user_agent, timeout=timeout).casefold()
    return next((phrase for phrase in CLOSED_LISTING_PHRASES if phrase in lowered), "")


def fetch_office_evidence(
    company_url: str,
    user_agent: str = "InternshipResearch/0.1",
    timeout: int = 10,
    max_pages: int = 3,
) -> Record | None:
    """First Bengaluru-office sentence on the company site, or None.

    Robots-respecting and never raising: a dead site is just no evidence.
    """

    base = canonical_url(company_url)
    if not base.startswith("http"):
        return None
    origin = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}"
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    robots = _robots(session, origin, timeout)
    fetched = 0
    try:
        for path in OFFICE_PATHS:
            if fetched >= max_pages:
                break
            url = urljoin(origin + "/", path.lstrip("/"))
            if not robots.can_fetch(user_agent, url):
                continue
            try:
                response = session.get(url, timeout=timeout)
            except requests.RequestException:
                continue
            if response.status_code >= 400 or "html" not in response.headers.get(
                "Content-Type", ""
            ):
                continue
            fetched += 1
            found = find_office_evidence(response.text, response.url)
            if found:
                return found
    except Exception:
        return None
    return None
