"""Free evidence read from a company's own website.

The strongest free signal about what a small company is actually doing is the
company's own about, product, careers, blog, or changelog page. This module
fetches a small number of those pages, respecting robots.txt, and turns them
into evidence entries carrying a URL and an access date. Nothing here infers,
summarizes beyond quoting, or invents: an entry is a real sentence that really
appears on a real page.
"""

from __future__ import annotations

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
    text = clean_text(soup.get_text(" ", strip=True))
    parts = re.split(r"(?<=[.!?])\s+", text)
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
OWNERSHIP_VERBS = (
    "own", "manage", "build", "coordinate", "track", "run", "streamline",
    "scale", "improve", "automate", "drive", "set up", "support",
)


# Feed and aggregator boilerplate that sits in the same field as the real
# description. Quoting it produced "Ressl AI (W26) Train, eval and build
# autonomous agents ( 2 days ago) GTM..." in a real run.
FEED_NOISE = ("days ago", "day ago", "hours ago", "apply now", "posted on")


def primary_responsibility(description: str) -> str:
    """The listing's own words for what the role will do. Never paraphrased."""

    candidates = [
        line
        for line in _sentences(str(description or "").replace(chr(65533), " "))
        if any(f"{verb} " in line.casefold() for verb in OWNERSHIP_VERBS)
        and not any(noise in line.casefold() for noise in FEED_NOISE)
    ]
    if not candidates:
        return ""
    # The longest qualifying sentence is the one that actually describes the
    # work; the first is often a header that happens to contain a verb.
    return max(candidates, key=len)

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
