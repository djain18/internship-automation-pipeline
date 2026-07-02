"""
api/main.py
-----------
FastAPI backend for the Dispatch website.

Routes:
  GET  /api/listings   — reads from Google Sheets (or seed JSON)
  GET  /api/stats      — pipeline stats for the masthead edition block
  POST /api/subscribe  — saves subscriber + sends welcome email via Resend

Environment variables (set in Railway/Render dashboard):
  GOOGLE_SHEET_ID      — the spreadsheet ID
  GOOGLE_API_KEY       — for a publicly-viewable sheet (simplest)
  RESEND_API_KEY       — for welcome emails
  FRONTEND_ORIGIN      — your Vercel domain for CORS
"""

from __future__ import annotations

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from sheets import fetch_listings, fetch_stats
import email_service

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Dispatch API", version="1.0.0")

# ── CORS ──────────────────────────────────────────────────────
FRONTEND = os.getenv("FRONTEND_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND] if FRONTEND != "*" else ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── GET /api/listings ─────────────────────────────────────────
@app.get("/api/listings")
async def get_listings():
    try:
        listings = await fetch_listings()
        return listings
    except Exception as e:
        log.error("Failed to fetch listings: %s", e)
        raise HTTPException(status_code=503, detail="Listings unavailable")


# ── GET /api/stats ────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    try:
        return await fetch_stats()
    except Exception as e:
        log.error("Failed to fetch stats: %s", e)
        raise HTTPException(status_code=503, detail="Stats unavailable")


# ── POST /api/subscribe ───────────────────────────────────────
class SubscribePayload(BaseModel):
    email: EmailStr
    roles: list[str] = []
    cities: list[str] = []
    remote: bool = True
    gradYear: str = "2027"


@app.post("/api/subscribe", status_code=201)
async def subscribe(payload: SubscribePayload):
    log.info("New subscriber: %s | roles=%s | cities=%s", payload.email, payload.roles, payload.cities)
    try:
        await email_service.add_contact(
            email=payload.email,
            roles=payload.roles,
            cities=payload.cities,
            remote=payload.remote,
            grad_year=payload.gradYear,
        )
        await email_service.send_welcome(
            email=payload.email,
            roles=payload.roles,
            cities=payload.cities,
        )
    except Exception as e:
        # Non-fatal — subscriber is logged, email might fail
        log.warning("Email service error for %s: %s", payload.email, e)

    return {"status": "ok", "email": payload.email}


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}
