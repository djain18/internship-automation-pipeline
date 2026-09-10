from __future__ import annotations

from models import Record, canonical_url, clean_text


def choose_contact(record: Record) -> Record:
    raw = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    email = clean_text(raw.get("email"))
    linkedin = canonical_url(raw.get("linkedin"))
    source_url = canonical_url(raw.get("source_url") or record.get("source_url"))
    if not any((raw.get("name"), email, linkedin)):
        return {
            "status": "contact_research_required",
            "confidence": "low",
            "source_url": source_url,
        }
    status = clean_text(raw.get("verification_status") or "unverified").casefold()
    confidence = "high" if status in {"published_by_source", "human_verified"} else "low"
    return {
        "status": "available",
        "name": clean_text(raw.get("name")),
        "role": clean_text(raw.get("role") or "hiring contact"),
        "email": email,
        "linkedin": linkedin,
        "source_url": source_url,
        "access_date": record.get("discovered_at"),
        "verification_status": status,
        "confidence": confidence,
    }


