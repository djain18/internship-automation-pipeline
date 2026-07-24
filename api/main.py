"""
api/main.py
-----------
FastAPI backend for the Dispatch website.

Routes:
  GET  /api/listings   — reads from Google Sheets (or seed JSON)
  GET  /api/stats      — pipeline stats for the masthead edition block

Environment variables (set in Railway/Render dashboard):
  GOOGLE_SHEET_ID      — the spreadsheet ID
  GOOGLE_API_KEY       — for a publicly-viewable sheet (simplest)
  FRONTEND_ORIGIN      — your Vercel domain for CORS
"""

from __future__ import annotations

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sheets import fetch_listings, fetch_stats

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


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}
