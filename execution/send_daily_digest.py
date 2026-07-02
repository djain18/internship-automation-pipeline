"""
send_daily_digest.py
--------------------
Sends the personalized daily internship digest that the welcome email promises.

Flow:
  1. Pull the current live listings from the deployed API (single source of truth).
  2. Pull subscribers from the Resend audience.
  3. For each subscriber, pick the freshest listings that match their saved
     roles/cities (or the overall freshest if they have no preferences).
  4. Send a clean, Rise-branded HTML digest via Resend.

Safe by default: with no RESEND_API_KEY it runs as a DRY RUN and just prints
what it would have sent, so it's harmless to invoke locally.

Env:
  RESEND_API_KEY, RESEND_AUDIENCE_ID   — delivery + subscriber list
  API_BASE                              — listings source (deployed FastAPI)
  SITE_URL, FROM_EMAIL                  — links + sender
"""

from __future__ import annotations

import os
import html
import logging

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("digest")

RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
RESEND_AUDIENCE = os.getenv("RESEND_AUDIENCE_ID", "")
API_BASE   = os.getenv("API_BASE", "https://rise-api-production-a6c4.up.railway.app").rstrip("/")
SITE_URL   = os.getenv("SITE_URL", "https://rise-web-kappa.vercel.app")
FROM_EMAIL = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
FROM_NAME  = "Rise"
BASE       = "https://api.resend.com"

MAX_ROLES_PER_DIGEST = 8


def fetch_listings() -> list[dict]:
    try:
        resp = requests.get(f"{API_BASE}/api/listings", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        log.error("Could not fetch listings: %s", e)
        return []


def fetch_contacts() -> list[dict]:
    if not RESEND_API_KEY or not RESEND_AUDIENCE:
        return []
    try:
        resp = requests.get(
            f"{BASE}/audiences/{RESEND_AUDIENCE}/contacts",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        contacts = resp.json().get("data", [])
        # Drop unsubscribed contacts.
        return [c for c in contacts if not c.get("unsubscribed")]
    except Exception as e:
        log.error("Could not fetch contacts: %s", e)
        return []


def _prefs(contact: dict) -> tuple[list[str], list[str]]:
    """Best-effort read of saved role/city preferences from a contact."""
    data = contact.get("data") or {}
    roles = [r.strip().lower() for r in str(data.get("roles", "")).split(",") if r.strip()]
    cities = [c.strip().lower() for c in str(data.get("cities", "")).split(",") if c.strip()]
    return roles, cities


def match_for(contact: dict, listings: list[dict]) -> list[dict]:
    """Freshest listings matching a subscriber's roles/cities (or overall freshest)."""
    roles, cities = _prefs(contact)
    fresh = sorted(listings, key=lambda x: x.get("hoursAgo", 99))

    if not roles and not cities:
        return fresh[:MAX_ROLES_PER_DIGEST]

    def hit(listing: dict) -> bool:
        hay_role = f"{listing.get('cluster','')} {listing.get('title','')}".lower()
        hay_city = str(listing.get("location", "")).lower()
        role_ok = not roles or any(r in hay_role for r in roles)
        city_ok = not cities or any(c in hay_city for c in cities)
        return role_ok and city_ok

    matched = [l for l in fresh if hit(l)]
    # Never send an empty digest — fall back to the overall freshest.
    return (matched or fresh)[:MAX_ROLES_PER_DIGEST]


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
      Rise · Free for students. Reply "unsubscribe" to stop these emails.
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
    contacts = fetch_contacts()

    if dry_run or not contacts:
        sample = match_for({}, listings)
        log.info("DRY RUN (no RESEND_API_KEY or no contacts). Sample digest of %d roles:", len(sample))
        for l in sample:
            log.info("  • %s @ %s (%s)", l.get("title"), l.get("org"), l.get("location"))
        return {"sent": 0, "listings": len(listings), "dry_run": True}

    sent = 0
    for c in contacts:
        email = c.get("email")
        if not email:
            continue
        picks = match_for(c, listings)
        if not picks:
            continue
        name = (c.get("first_name") or "").strip()
        if send(email, build_html(name, picks), len(picks)):
            sent += 1

    log.info("Digest complete: sent %d/%d subscribers", sent, len(contacts))
    return {"sent": sent, "subscribers": len(contacts), "listings": len(listings)}


if __name__ == "__main__":
    main()
