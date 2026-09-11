from __future__ import annotations

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


def choose_contact(record: Record) -> Record:
    raw = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    email = clean_text(raw.get("email"))
    linkedin = canonical_url(raw.get("linkedin"))
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
    return {
        "status": "available",
        "name": clean_text(raw.get("name")),
        "role": clean_text(raw.get("role") or "hiring contact"),
        "email": email,
        "linkedin": linkedin,
        "source_url": source_url,
        "access_date": access_date,
        "verification_status": status,
        "basis": "record_contact",
        "confidence": confidence,
        "contact_priority": (
            "preferred_named" if mailbox_kind == "named" and raw.get("name")
            else "fallback_generic" if mailbox_kind == "generic_fallback"
            else "unverified_lead"
        ),
    }
