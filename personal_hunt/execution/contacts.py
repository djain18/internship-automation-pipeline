from __future__ import annotations

import re

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


def _mailbox_kind(email: str) -> str:
    lowered = email.casefold().strip()
    if any(lowered.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return "excluded"
    if any(lowered.startswith(prefix) for prefix in ALLOWED_FALLBACK_PREFIXES):
        return "generic_fallback"
    return "named"


def _site_email(record: Record) -> tuple[str, str]:
    """The best address published on the company's own site, if any.

    Returns (email, kind). A personal-looking address beats a shared mailbox,
    because a shared mailbox rarely reaches the person who decides.
    """

    published = [
        clean_text(item)
        for item in (record.get("research") or {}).get("published_emails") or []
    ]
    if not published:
        return "", ""
    direct = [
        item
        for item in published
        if _mailbox_kind(item) == "named"
    ]
    if direct:
        return direct[0], "site_published_direct"
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


def choose_contact(record: Record) -> Record:
    raw = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    email = clean_text(raw.get("email"))
    linkedin = _extract_provenanced_linkedin(record)
    source_url = canonical_url(raw.get("source_url") or record.get("source_url"))
    access_date = record.get("discovered_at") or record.get("access_date")
    if not any((raw.get("name"), email, linkedin)):
        # Nothing came with the record. Fall back to what the company itself
        # published on a page this pipeline actually fetched and can cite.
        site_email, kind = _site_email(record)
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
            "source_url": canonical_url(record.get("company_url")) or source_url,
            "access_date": access_date,
            "verification_status": "published_by_source",
            "basis": kind,
            # Published by the company, but not confirmed as the right person.
            "confidence": "medium",
            "contact_priority": (
                "preferred_named" if kind == "site_published_direct" else "fallback_generic"
            ),
        }
    status = clean_text(raw.get("verification_status") or "unverified").casefold()
    mailbox_kind = _mailbox_kind(email) if email else "named"
    if mailbox_kind == "excluded":
        email = ""
        if not any((raw.get("name"), linkedin)):
            return {
                "status": "contact_research_required",
                "confidence": "low",
                "source_url": source_url,
                "reason": "excluded_unrelated_mailbox",
            }
    if mailbox_kind == "generic_fallback" and status not in TRUSTED_STATUSES:
        email = ""
        mailbox_kind = "unverified_generic"
    confidence = "high" if status in TRUSTED_STATUSES else "low"
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
        "verification_status": status,
        "basis": "record_contact",
        "confidence": confidence,
        "contact_priority": priority,
    }
