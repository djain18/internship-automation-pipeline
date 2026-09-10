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
        if not any(item.casefold().startswith(prefix) for prefix in ROLE_MAILBOXES)
    ]
    if direct:
        return direct[0], "site_published_direct"
    return published[0], "site_published_role_mailbox"


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
        }
    status = clean_text(raw.get("verification_status") or "unverified").casefold()
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
    }
