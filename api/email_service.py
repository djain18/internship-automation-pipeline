"""
email_service.py
----------------
Sends welcome emails and manages contacts via Resend.
Free tier: 3,000 emails/month, 100/day.
https://resend.com/docs/api-reference/contacts

Set RESEND_API_KEY in the Railway/Render environment.
If key is absent, all operations are no-ops (safe for local dev).
"""

from __future__ import annotations

import os
import logging
import httpx

log = logging.getLogger(__name__)

RESEND_API_KEY    = os.getenv("RESEND_API_KEY", "")
RESEND_AUDIENCE   = os.getenv("RESEND_AUDIENCE_ID", "")
# Default to Resend's shared sending domain so the free tier works without a
# verified custom domain. Override with a verified FROM_EMAIL in production.
FROM_EMAIL        = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
FROM_NAME         = "Rise"
SITE_URL          = os.getenv("SITE_URL", "https://rise-web-kappa.vercel.app")
BASE              = "https://api.resend.com"


def _headers():
    return {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}


async def add_contact(email: str, roles: list, cities: list, remote: bool, grad_year: str):
    if not RESEND_API_KEY or not RESEND_AUDIENCE:
        log.info("[email_service] No key/audience — skipping contact upsert for %s", email)
        return

    payload = {
        "email": email,
        "first_name": "",
        "unsubscribed": False,
        "data": {
            "roles":     ",".join(roles),
            "cities":    ",".join(cities),
            "remote":    str(remote),
            "grad_year": grad_year,
        },
    }
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.post(
            f"{BASE}/audiences/{RESEND_AUDIENCE}/contacts",
            json=payload,
            headers=_headers(),
        )
        if resp.status_code not in (200, 201):
            log.warning("Resend contact upsert returned %s: %s", resp.status_code, resp.text)


async def send_welcome(email: str, roles: list, cities: list):
    if not RESEND_API_KEY:
        log.info("[email_service] No key — skipping welcome email to %s", email)
        return

    roles_str  = " · ".join(roles[:4]) if roles  else "your fields"
    cities_str = ", ".join(cities[:3]) if cities else "your cities"

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Inter, Helvetica, Arial, sans-serif; background: #f5f5f7; color: #18181b; margin: 0; padding: 0; }}
  .wrap {{ max-width: 560px; margin: 40px auto; background: #ffffff; border: 1px solid #ececf1; border-radius: 16px; overflow: hidden; }}
  .head {{ padding: 28px 32px 0; }}
  .name {{ font-size: 1.6rem; font-weight: 700; letter-spacing: -.02em; color: #4f46e5; }}
  .body {{ padding: 8px 32px 4px; font-size: 1rem; line-height: 1.6; }}
  .stamp {{ display: inline-block; background: #eef2ff; color: #4f46e5; font-size: .68rem; letter-spacing: .1em; font-weight: 700; padding: 5px 10px; border-radius: 999px; }}
  .receipt {{ margin: 20px 32px; border: 1px solid #ececf1; border-radius: 12px; overflow: hidden; }}
  .row {{ display: flex; justify-content: space-between; padding: 12px 16px; border-top: 1px solid #f0f0f4; font-size: .9rem; }}
  .row:first-child {{ border-top: none; }}
  .btn {{ display: inline-block; background: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: .9rem; font-weight: 600; border-radius: 10px; }}
  .cta {{ padding: 4px 32px 28px; }}
  .fine {{ padding: 20px 32px 28px; border-top: 1px solid #f0f0f4; font-size: .72rem; color: #9797a3; line-height: 1.6; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="name">Rise</div>
  </div>

  <div class="body">
    <span class="stamp">✓ SUBSCRIBED</span>
    <p style="margin-top:18px;">You're on the list.</p>
    <p>
      Your first daily digest lands <strong>tomorrow at 8:00 AM IST</strong> — tuned to
      <strong>{roles_str}</strong> in <strong>{cities_str}</strong>.
    </p>
    <p>
      Every night we read the internships posted across LinkedIn, filter out the fee scams
      and the roles you can't apply to from India, and send you only what's real, fresh, and
      open. One email a day. Unsubscribe anytime.
    </p>
  </div>

  <div class="receipt">
    <div class="row"><span>Fields</span><span><strong>{roles_str}</strong></span></div>
    <div class="row"><span>Cities</span><span><strong>{cities_str}</strong></span></div>
    <div class="row"><span>Digest time</span><span><strong>08:00 IST</strong></span></div>
  </div>

  <div class="cta">
    <a class="btn" href="{SITE_URL}">Browse internships →</a>
  </div>

  <p class="fine">
    Rise · Free for students. No ads. No data sold.<br>
    To unsubscribe, reply with "unsubscribe" — or use the link in any future digest.
  </p>
</div>
</body>
</html>
"""

    payload = {
        "from":    f"{FROM_NAME} <{FROM_EMAIL}>",
        "to":      [email],
        "subject": "You're on the list — your first Rise digest arrives tomorrow at 8 AM.",
        "html":    html,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BASE}/emails", json=payload, headers=_headers())
        if resp.status_code not in (200, 201):
            log.warning("Resend send returned %s: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Resend error {resp.status_code}")
        log.info("Welcome email sent to %s", email)
