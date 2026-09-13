from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from models import Record, canonical_url, clean_text

# A published address is only as good as where it was published. These two are
# the only statuses allowed to read as high confidence; everything else is a
# lead Daksh confirms himself. No address is ever guessed or pattern-generated
# from a name and a domain - a guessed email is not a contact.
TRUSTED_STATUSES = {"published_by_source", "human_verified"}

# Addresses that reach a shared queue, not a person. Worth having, never worth
# calling a named contact.
ROLE_MAILBOXES = (
    "info@", "hello@", "contact@", "support@", "admin@", "sales@",
    "careers@", "jobs@", "hr@", "press@", "noreply@", "no-reply@",
)

ALLOWED_FALLBACK_PREFIXES = ("careers@", "jobs@", "founder@", "founders@", "hello@")
EXCLUDED_PREFIXES = (
    "support@", "press@", "media@", "pr@", "sales@", "admin@", "noreply@",
    "no-reply@", "privacy@", "legal@", "security@", "billing@",
)

# Prefixes that are never a hiring channel even when a listing prints them.
# Deliberately shorter than EXCLUDED_PREFIXES: that list exists for addresses
# scraped off a company site, where admin@/hr@/info@ is a webmaster or a
# billing queue. A hiring post that writes "send your resume to admin@..." is
# naming its application channel, and dropping it there threw away the real
# contact (Auraaison's Founder's Office Intern post, 2026-09-12).
LISTING_NOISE_PREFIXES = (
    "noreply@", "no-reply@", "donotreply@", "privacy@", "legal@",
    "security@", "billing@", "press@", "media@", "pr@", "abuse@",
)

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def listing_emails(record: Record) -> list[str]:
    """Addresses the listing itself published, in the order it published them.

    26% of the LinkedIn hiring posts this pipeline already pays for print an
    application address in the post body (admin@auraaison.com,
    careers@ethereallabs.in, hr@anumak.com). Nothing read them, so records
    that shipped a usable contact still reached Daksh as
    contact_research_required. The post URL is the provenance -- this is a
    public professional channel the employer published itself, not a guess.
    """
    # The job page behind the link counts as the listing too.
    text = f"{record.get('description', '')} {record.get('listing_page_text', '')}"
    found: list[str] = []
    for match in _EMAIL_PATTERN.findall(text):
        email = match.strip(".,;:)'\"").casefold()
        lowered = email.casefold()
        if any(lowered.startswith(prefix) for prefix in LISTING_NOISE_PREFIXES):
            continue
        if lowered.rsplit("@", 1)[-1] in PLACEHOLDER_EMAIL_DOMAINS:
            continue
        if email not in found:
            found.append(email)
    return found


def _mailbox_kind(email: str) -> str:
    lowered = email.casefold().strip()
    if any(lowered.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return "excluded"
    # ROLE_MAILBOXES was defined and never consulted, so info@kplor.com came
    # back "named" and ranked as a person (live comparison, 2026-09-13).
    if any(lowered.startswith(prefix) for prefix in (*ALLOWED_FALLBACK_PREFIXES, *ROLE_MAILBOXES)):
        return "generic_fallback"
    return "named"


# Documentation and template pages print these as examples.
PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com", "example.org", "company.com", "domain.com", "email.com",
    "yourcompany.com", "yourdomain.com", "test.com", "sentry.io",
}


def _registrable_domain(host: str) -> str:
    labels = host.casefold().removeprefix("www.").split(".")
    keep = 3 if len(labels) >= 3 and labels[-2] in {"co", "com", "org", "net", "ac"} else 2
    return ".".join(labels[-keep:])


def _belongs_to_site(email: str, company_url: str) -> bool:
    """A site-scraped address counts only on the company's own domain.

    The deep-research comparison resolved SuprSend to docs.suprsend.com and
    took dev@company.com -- an example in their API docs -- as the contact.
    """
    domain = email.rsplit("@", 1)[-1].casefold()
    host = urlsplit(canonical_url(company_url)).netloc
    if host:
        return _registrable_domain(domain) == _registrable_domain(host)
    return domain not in PLACEHOLDER_EMAIL_DOMAINS


def _published_source_url(record: Record, kind: str, source_url: str) -> str:
    """Where a published address was actually read. A listing-sourced address
    is cited to the listing, not to a company page that may never have been
    fetched."""
    if kind.startswith("listing_"):
        return canonical_url(record.get("source_url")) or source_url
    return canonical_url(record.get("company_url")) or source_url


def _site_email(record: Record) -> tuple[str, str]:
    """The best published address for this record, if any.

    Returns (email, kind). A personal-looking address beats a shared mailbox,
    because a shared mailbox rarely reaches the person who decides. Reads
    both research and deep_problem_research -- same two-source merge
    _extract_provenanced_linkedin already does, since a discovered/watchlist
    company's emails live in the latter, not the former, and reading only
    "research" silently dropped every one of them.
    """
    research = record.get("research") if isinstance(record.get("research"), dict) else {}
    deep_research = record.get("deep_problem_research") if isinstance(record.get("deep_problem_research"), dict) else {}
    published = [
        clean_text(item)
        for item in [
            *(research.get("published_emails") or []),
            *(deep_research.get("published_emails") or []),
        ]
        if _belongs_to_site(clean_text(item), str(record.get("company_url") or ""))
    ]
    listing = listing_emails(record)
    if not published and not listing:
        return "", ""
    # A named person on the company's own site is the strongest published
    # address. Below that, the address the listing names for THIS role beats a
    # generic mailbox scraped off a site footer, because the listing's address
    # is the channel the employer asked applicants to use.
    direct = [item for item in published if _mailbox_kind(item) == "named"]
    if direct:
        return direct[0], "site_published_direct"
    listing_named = [item for item in listing if _mailbox_kind(item) == "named"]
    if listing_named:
        return listing_named[0], "listing_published_direct"
    if listing:
        return listing[0], "listing_published_role_mailbox"
    fallback = [item for item in published if _mailbox_kind(item) == "generic_fallback"]
    if fallback:
        return fallback[0], "site_published_role_mailbox"
    return "", ""


def _profile_belongs_to(url: str, name: str) -> bool:
    """True when a published /in/ profile URL is demonstrably this person's.

    company_site.fetch_site_evidence scrapes every linkedin.com/in/ link on a
    team or about page, so the list is "some humans at this company", not
    "the contact". Stamping the first one onto whichever contact was chosen
    attributes a real person's profile to someone else, which is inventing a
    contact. Require every meaningful token of the contact's name to appear
    in the profile slug; anything less stays empty.
    """
    slug = url.casefold().rsplit("/in/", 1)[-1]
    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", clean_text(name).casefold())
        if len(token) > 2
    ]
    return bool(slug) and bool(tokens) and all(token in slug for token in tokens)


def _extract_provenanced_linkedin(record: Record) -> str:
    """Extract a LinkedIn profile URL from provenanced sources only.

    Allowed sources:
    1. Explicitly in the contact record (Hunter result)
    2. Published on the company's own site (team/about pages), and only when
       the profile slug matches the contact's own name
    3. Apify public-post author field (if implemented)

    Never construct or guess from name/email.
    """
    # 1. Check if already in contact record (from Hunter or other source)
    raw = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    if raw.get("linkedin"):
        url = canonical_url(raw.get("linkedin"))
        if url and "linkedin.com" in url.casefold():
            return url

    # 2/3. Scraped site profiles, from the opportunity's own research or from
    # deep problem research. Only a name match makes one of these this
    # contact's profile rather than a colleague's.
    name = clean_text(raw.get("name"))
    if not name:
        return ""
    research = record.get("research") if isinstance(record.get("research"), dict) else {}
    deep_research = record.get("deep_problem_research") if isinstance(record.get("deep_problem_research"), dict) else {}
    published_urls = [
        *(research.get("published_linkedin_urls") or []),
        *(deep_research.get("published_linkedin_urls") or []),
    ]
    for candidate in published_urls:
        url = canonical_url(candidate)
        if url and _profile_belongs_to(url, name):
            return url

    return ""


def _role_priority(role: str) -> int:
    """Score a contact role for priority. Lower is better (for sorting).

    Prefers: founder, chief of staff, head of ops, then named contact,
    then generic/research-required fallback.
    """
    if not role:
        return 999
    role_lower = clean_text(role).casefold()
    if any(term in role_lower for term in ("founder", "co-founder", "cofounder")):
        return 1
    if "chief of staff" in role_lower or "coo" in role_lower:
        return 2
    if "head of ops" in role_lower or "vp ops" in role_lower or "director of ops" in role_lower:
        return 3
    return 50  # Named person with generic role


def attach_contact(record: Record, hunter_ctx: dict[str, Any] | None) -> Record:
    """choose_contact, then one bounded Hunter lookup when it found no email.

    The single path all three contact-attaching call sites route through
    (enrich_selected's research queue, funding events, and watchlist/
    discovered-for-research companies) -- previously only the first of
    those three ever reached Hunter, so the highest-value targets (the ones
    that get deep research and a validated prototype prompt) never got a
    contact lookup at all. hunter is imported here, not at module level,
    because hunter.py imports _mailbox_kind from this module.
    """
    contact = choose_contact(record)
    if hunter_ctx and not (contact or {}).get("email"):
        from hunter import find_company_contact_with_status

        found, status = find_company_contact_with_status(
            record, hunter_ctx["scoring"], hunter_ctx["state"], hunter_ctx["month"]
        )
        # Collected here, read once at the end of run_pipeline to build a
        # single "hunter" source_health row -- every early return used to
        # look identical (silent None) from outside, which let a missing
        # HUNTER_API_KEY go unnoticed for weeks.
        hunter_ctx.setdefault("statuses", []).append(status)
        if found and found.get("email"):
            return found
    return contact


def choose_contact(record: Record) -> Record:
    raw = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    email = clean_text(raw.get("email"))
    linkedin = _extract_provenanced_linkedin(record)
    source_url = canonical_url(raw.get("source_url") or record.get("source_url"))
    access_date = record.get("discovered_at") or record.get("access_date")
    site_email, kind = _site_email(record)
    if not any((raw.get("name"), email, linkedin)):
        # Nothing came with the record. Fall back to what the company itself
        # published -- on a page this pipeline fetched, or in the listing text.
        if not site_email:
            return {
                "status": "contact_research_required",
                "confidence": "low",
                "source_url": source_url,
            }
        return {
            "status": "available",
            "name": "",
            "role": "published company address",
            "email": site_email,
            "linkedin": "",
            "source_url": _published_source_url(record, kind, source_url),
            "access_date": access_date,
            "verification_status": "published_by_source",
            "basis": kind,
            # Published by the company, but not confirmed as the right person.
            "confidence": "medium",
            "contact_priority": (
                "preferred_named"
                if kind in {"site_published_direct", "listing_published_direct"}
                else "fallback_generic"
            ),
        }
    status = clean_text(raw.get("verification_status") or "unverified").casefold()
    mailbox_kind = _mailbox_kind(email) if email else "named"
    if mailbox_kind == "excluded":
        email = ""
        if not any((raw.get("name"), linkedin, site_email)):
            return {
                "status": "contact_research_required",
                "confidence": "low",
                "source_url": source_url,
                "reason": "excluded_unrelated_mailbox",
            }
    if mailbox_kind == "generic_fallback" and status not in TRUSTED_STATUSES:
        email = ""
        mailbox_kind = "unverified_generic"
    basis = "record_contact"
    confidence = "high" if status in TRUSTED_STATUSES else "low"
    # A record carrying a name or a LinkedIn URL but no usable email used to
    # skip the published-address lookup entirely, because that lookup lived
    # inside the "nothing came with the record" branch. The listing's own
    # application address is exactly what such a record is missing. Confidence
    # stays medium, matching the other published-address branch: the employer
    # published it, but nobody confirmed it reaches the right person.
    if not email and site_email:
        email = site_email
        basis = kind
        mailbox_kind = _mailbox_kind(site_email)
        confidence = "medium"
    role_str = clean_text(raw.get("role") or "hiring contact")
    role_score = _role_priority(role_str)

    # Determine contact priority: role-based scores, then fallback to mailbox kind
    if mailbox_kind == "named" and raw.get("name"):
        # Named contact: score by role seniority. Founder / chief of staff /
        # head of ops rank above a named person with a generic role, which is
        # the ladder Phase 4 asked for; collapsing both into "preferred_named"
        # made _role_priority decorative.
        priority = "preferred_named_senior" if role_score <= 3 else "preferred_named"
    elif mailbox_kind == "generic_fallback":
        priority = "fallback_generic"
    else:
        priority = "unverified_lead"

    return {
        "status": "available",
        "name": clean_text(raw.get("name")),
        "role": role_str,
        "email": email,
        "linkedin": linkedin,
        "source_url": source_url,
        "access_date": access_date,
        "verification_status": (
            "published_by_source" if basis != "record_contact" else status
        ),
        "basis": basis,
        "confidence": confidence,
        "contact_priority": priority,
    }
