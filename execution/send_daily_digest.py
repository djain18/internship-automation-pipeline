"""
send_daily_digest.py
--------------------
Sends the personalized daily internship digest that the welcome email promises.

Flow:
  1. Pull the current live listings from the deployed API (single source of truth).
  2. Pull subscribers from Firestore's users/ collection (via firebase-admin).
  3. For each subscriber, pick the freshest listings that match their saved
     roles/cities (or the overall freshest if they have no preferences).
  4. Send a clean, Rise-branded HTML digest via Resend.

Safe by default: with no RESEND_API_KEY it runs as a DRY RUN and just prints
what it would have sent, so it's harmless to invoke locally.

Env:
  RESEND_API_KEY               — delivery (still used for sending)
  FIREBASE_SERVICE_ACCOUNT_JSON — Firestore subscriber source
  API_BASE                      — listings source (deployed FastAPI)
  SITE_URL, FROM_EMAIL          — links + sender
"""

from __future__ import annotations

import os
import html
import logging
import tempfile

import requests

try:
    from execution import role_taxonomy
except ImportError:
    import role_taxonomy

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("digest")

RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
API_BASE   = os.getenv("API_BASE", "https://dakshinjain187--internship-pipeline-api-web.modal.run").rstrip("/")
SITE_URL   = os.getenv("SITE_URL", "https://rise-web-kappa.vercel.app")
FROM_EMAIL = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
FROM_NAME  = "Rise"
BASE       = "https://api.resend.com"

SENT_HISTORY_CAP = 300  # how many past listing ids we remember per subscriber
# Last-mile role cap. The sheet itself is now balanced by role_taxonomy.balance
# at scrape time, but this guarantees a single email can never become one role
# even if a night skews — which is what produced the all-marketing digest this
# was added to fix.
DIGEST_MAX_PER_ROLE = 3


def fetch_listings() -> list[dict]:
    try:
        resp = requests.get(f"{API_BASE}/api/listings", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        log.error("Could not fetch listings: %s", e)
        return []


def _firestore_client():
    """Init (once) and return the Admin SDK Firestore client, or None if
    credentials aren't configured (local dry run)."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        log.error("firebase-admin not installed — cannot reach Firestore.")
        return None

    if not firebase_admin._apps:
        cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        if not cred_json:
            log.warning("FIREBASE_SERVICE_ACCOUNT_JSON not set — skipping (dry run).")
            return None
        # tempfile.gettempdir(), not a hardcoded "/tmp" — this runs both in
        # Modal (Linux) and locally (Windows, during manual verification).
        cred_path = os.path.join(tempfile.gettempdir(), "firebase-admin-key.json")
        with open(cred_path, "w", encoding="utf-8") as f:
            f.write(cred_json)
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    return firestore.client()


def fetch_contacts(db) -> list[dict]:
    """Read all subscriber preference docs from Firestore's users/ collection.
    Each contact dict carries its doc id as "_uid" so a digest send can be
    recorded back against the right subscriber."""
    if db is None:
        return []
    try:
        docs = db.collection("users").stream()
        contacts = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["_uid"] = doc.id
            contacts.append(data)
        return contacts
    except Exception as e:
        log.error("Could not fetch Firestore subscribers: %s", e)
        return []


def _exclude_sent(candidates: list[dict], already_sent: list[str]) -> list[dict]:
    """Drop listings this subscriber was already emailed, so a thin-supply
    day skips rather than resends yesterday's picks under a "new" subject."""
    already_sent_set = set(already_sent)
    return [l for l in candidates if l.get("id") not in already_sent_set]


def mark_sent(db, uid: str, sent_ids: list[str], already_sent: list[str]) -> None:
    """Record the listing ids just emailed so tomorrow's digest excludes them.
    Caps the stored history so the doc never grows unbounded."""
    if db is None or not uid:
        return
    merged = already_sent + [i for i in sent_ids if i not in already_sent]
    merged = merged[-SENT_HISTORY_CAP:]
    try:
        db.collection("users").document(uid).update({"sent_listing_ids": merged})
    except Exception as e:
        log.warning("Could not record sent_listing_ids for %s: %s", uid, e)


def _prefs(contact: dict) -> tuple[list[str], list[str]]:
    """Best-effort read of a subscriber's saved role/city preferences.
    Firestore stores roles/cities as real lists (unlike Resend's
    comma-joined custom fields) — tolerate a malformed doc rather than
    crash, since one bad record must not kill the whole digest run."""
    raw_roles = contact.get("roles")
    raw_cities = contact.get("cities")
    roles = [r.strip().lower() for r in raw_roles if isinstance(r, str) and r.strip()] if isinstance(raw_roles, list) else []
    cities = [c.strip().lower() for c in raw_cities if isinstance(c, str) and c.strip()] if isinstance(raw_cities, list) else []
    return roles, cities


def match_for(contact: dict, listings: list[dict]) -> list[dict]:
    """All fresh listings matching a subscriber's roles/cities, no cap.

    Tries progressively looser tiers and returns the first one that finds
    anything, so a dry night for a narrow preference set surfaces adjacent
    roles or cities instead of jumping straight to unrelated listings:
      1. role and city both match
      2. role matches, any city
      3. city matches, any role
      4. freshest overall (also used when the subscriber has no prefs at all)
    """
    roles, cities = _prefs(contact)
    fresh = sorted(listings, key=lambda x: x.get("hoursAgo", 99))

    if not roles and not cities:
        return fresh

    def role_hit(listing: dict) -> bool:
        hay_role = f"{listing.get('cluster','')} {listing.get('title','')}".lower()
        return any(r in hay_role for r in roles)

    def city_hit(listing: dict) -> bool:
        hay_city = str(listing.get("location", "")).lower()
        return any(c in hay_city for c in cities)

    if roles and cities:
        both = [l for l in fresh if role_hit(l) and city_hit(l)]
        if both:
            return both

    if roles:
        role_only = [l for l in fresh if role_hit(l)]
        if role_only:
            return role_only

    if cities:
        city_only = [l for l in fresh if city_hit(l)]
        if city_only:
            return city_only

    return fresh


def diversify(listings: list[dict], max_per_role: int = DIGEST_MAX_PER_ROLE) -> list[dict]:
    """Cap each role track and interleave, preserving freshness order within a role.

    Listings already carry `cluster` from the API, so this maps that label back
    to its quota track rather than re-classifying titles — Marketing and Content
    are separate chips on the site but one bucket here, which is what stops a
    "3 marketing + 3 content" email from reading as six marketing roles.

    Round-robin across tracks means the first few rows of the email always show
    different roles, which is what the reader actually sees.
    """
    if not listings:
        return []

    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for l in listings:
        track = role_taxonomy.track_for_cluster(l.get("cluster") or "")
        if track not in buckets:
            buckets[track] = []
            order.append(track)
        if len(buckets[track]) < max_per_role:
            buckets[track].append(l)

    out = []
    while any(buckets[t] for t in order):
        for track in order:
            if buckets[track]:
                out.append(buckets[track].pop(0))
    return out


def _apply_url(listing: dict) -> str:
    return (
        listing.get("applyLink")
        or listing.get("postUrl")
        or (f"mailto:{listing['contact']}" if listing.get("contact") else SITE_URL)
    )


def build_html(name: str, listings: list[dict]) -> str:
    rows = []
    for l in listings:
        title = html.escape(l.get("title", "Internship"))
        org = html.escape(l.get("org", ""))
        loc = html.escape(l.get("location", ""))
        stipend = l.get("stipend", 0)
        stipend_str = f"₹{int(stipend):,}/mo" if stipend else "Stipend undisclosed"
        url = html.escape(_apply_url(l))
        rows.append(f"""
        <tr>
          <td style="padding:14px 16px;border-top:1px solid #f0f0f4;">
            <div style="font-weight:600;color:#18181b;">{title}</div>
            <div style="font-size:.85rem;color:#71717a;">{org} · {loc} · {stipend_str}</div>
          </td>
          <td style="padding:14px 16px;border-top:1px solid #f0f0f4;text-align:right;white-space:nowrap;">
            <a href="{url}" style="color:#4f46e5;font-weight:600;text-decoration:none;font-size:.85rem;">Apply →</a>
          </td>
        </tr>""")

    return f"""
<!DOCTYPE html><html><body style="margin:0;background:#f5f5f7;font-family:-apple-system,'Segoe UI',Inter,Arial,sans-serif;color:#18181b;">
  <div style="max-width:600px;margin:32px auto;background:#fff;border:1px solid #ececf1;border-radius:16px;overflow:hidden;">
    <div style="padding:24px 32px 8px;">
      <div style="font-size:1.5rem;font-weight:700;color:#4f46e5;">Rise</div>
      <div style="color:#71717a;font-size:.9rem;">Today's verified internships{f', {html.escape(name)}' if name else ''}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;">{''.join(rows)}</table>
    <div style="padding:20px 32px;">
      <a href="{SITE_URL}/internships" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:11px 22px;border-radius:10px;font-size:.9rem;font-weight:600;">See all internships →</a>
    </div>
    <div style="padding:16px 32px 24px;border-top:1px solid #f0f0f4;font-size:.72rem;color:#9797a3;">
      Rise · Free for students. Reply "unsubscribe" to stop receiving these emails.
    </div>
  </div>
</body></html>"""


def send(email: str, html_body: str, count: int) -> bool:
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [email],
        "subject": f"{count} new verified internships for you today",
        "html": html_body,
    }
    resp = requests.post(
        f"{BASE}/emails",
        json=payload,
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        log.warning("Send to %s failed %s: %s", email, resp.status_code, resp.text)
        return False
    return True


def main() -> dict:
    listings = fetch_listings()
    log.info("Fetched %d live listings", len(listings))
    if not listings:
        log.warning("No listings — nothing to send.")
        return {"sent": 0, "listings": 0}

    dry_run = not RESEND_API_KEY
    db = _firestore_client()
    contacts = fetch_contacts(db)

    if dry_run or not contacts:
        sample = diversify(match_for({}, listings))
        log.info("DRY RUN (no RESEND_API_KEY or no contacts). Sample digest of %d roles:", len(sample))
        for l in sample:
            log.info("  • %s @ %s (%s)", l.get("title"), l.get("org"), l.get("location"))
        return {"sent": 0, "listings": len(listings), "dry_run": True}

    sent = 0
    skipped_no_new = 0
    for c in contacts:
        try:
            email = c.get("email")
            if not email:
                continue
            already_sent = c.get("sent_listing_ids") or []
            candidates = match_for(c, listings)
            # Diversify AFTER excluding already-sent, so the per-role cap
            # operates on what is genuinely new to this subscriber rather than
            # spending its slots on listings they'll never see.
            picks = diversify(_exclude_sent(candidates, already_sent))
            if not picks:
                # Nothing genuinely new for this subscriber today — sending
                # would just repeat yesterday's mail under a "new internships"
                # subject, which is exactly the bug this guards against.
                skipped_no_new += 1
                continue
            name = (c.get("first_name") or "").strip()
            if send(email, build_html(name, picks), len(picks)):
                sent += 1
                mark_sent(db, c.get("_uid"), [l["id"] for l in picks if l.get("id")], already_sent)
        except Exception as e:
            log.error("Skipping subscriber %s due to error: %s", c.get("email", "<unknown>"), e)
            continue

    log.info(
        "Digest complete: sent %d/%d subscribers (%d skipped — no new listings since last send)",
        sent, len(contacts), skipped_no_new,
    )
    return {
        "sent": sent,
        "subscribers": len(contacts),
        "listings": len(listings),
        "skipped_no_new": skipped_no_new,
    }


if __name__ == "__main__":
    main()
