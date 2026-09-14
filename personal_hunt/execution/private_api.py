from __future__ import annotations

import hmac
import json
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

import outreach_store


APPROVED_EMAILS = frozenset(
    value.strip().casefold()
    for value in os.getenv(
        "PERSONAL_APPROVED_EMAILS",
        "dakshinjain187@gmail.com,dakshjainn02@gmail.com",
    ).split(",")
    if value.strip()
)
OUTPUT_ROOT = Path(os.getenv("PIPELINE_OUTPUT_DIR", "/data/out")).resolve()
STATE_PATH = Path(os.getenv("PIPELINE_STATE_DIR", "/data/state")) / "state.json"
OUTREACH_PATH = STATE_PATH.with_name("outreach.json")
# Set by deploy/modal_app.py to volume.commit so writes reach the sender's container.
COMMIT: Any = lambda: None  # noqa: E731
_OUTREACH_LOCK = threading.Lock()


def _origins() -> list[str]:
    configured = os.getenv(
        "PERSONAL_FRONTEND_ORIGINS",
        "https://rise-web-kappa.vercel.app,http://localhost:5173",
    )
    return [value.strip() for value in configured.split(",") if value.strip()]


app = FastAPI(title="Rise Personal Hunt API", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def no_store(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _verify_token(raw_token: str) -> dict[str, Any]:
    try:
        import firebase_admin
        from firebase_admin import auth, credentials

        if not firebase_admin._apps:
            raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
            if not raw:
                raise RuntimeError("Firebase service account is not configured")
            firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)))
        return dict(auth.verify_id_token(raw_token, check_revoked=True))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired sign-in") from exc


def require_daksh(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in is required")
    claims = _verify_token(authorization[7:].strip())
    email = str(claims.get("email") or "").casefold()
    if not claims.get("email_verified") or email not in APPROVED_EMAILS:
        raise HTTPException(status_code=403, detail="This private hunt belongs to another account")
    return claims


def _latest_live() -> dict[str, Any]:
    pointer_path = OUTPUT_ROOT / "latest-live.json"
    if not pointer_path.is_file():
        raise HTTPException(status_code=404, detail="No live personal-hunt run is available")
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        run_path = Path(str(pointer.get("path") or "")).resolve()
        if OUTPUT_ROOT not in run_path.parents or not run_path.is_file():
            raise ValueError("latest-live path is invalid")
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Latest run could not be loaded") from exc
    if run.get("run_kind") != "live" or run.get("run_id") != pointer.get("run_id"):
        raise HTTPException(status_code=503, detail="Latest run pointer failed validation")
    # A failed Kimi gate used to 503 the whole page. The pointer is written on
    # every live run, so one Bedrock outage hid the funding signals, the
    # verification tray, the send queue and source health for the day -- none
    # of which depend on Kimi. Nothing unapproved is exposed by serving it:
    # digest_primary only ever holds records that passed the gate. The page
    # shows the failure as a banner (run.digestUsable) instead of an error.
    return run


def _sanitize(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if not isinstance(value, dict):
        return value
    output: dict[str, Any] = {}
    for key, item in value.items():
        lowered = str(key).casefold()
        if key.startswith("_") or lowered.endswith("_path"):
            continue
        if any(secret in lowered for secret in ("token", "credential", "authorization")):
            continue
        output[str(key)] = _sanitize(item)
    return output


def _apify_summary() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"month_spend_usd": 0, "monthly_hard_stop_usd": 5}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        month = date.today().strftime("%Y-%m")
        runs = ((state.get("apify_spend") or {}).get(month) or {}).get("runs") or {}
        spend = sum(float(item.get("usage_total_usd") or 0) for item in runs.values())
        return {
            "month": month,
            "month_spend_usd": round(spend, 4),
            "monthly_hard_stop_usd": 5,
            "run_count": len(runs),
        }
    except Exception:
        return {"month_spend_usd": 0, "monthly_hard_stop_usd": 5, "status": "unavailable"}


def _now() -> datetime:
    return datetime.now(outreach_store.IST)


def require_routine(authorization: str | None = Header(default=None)) -> None:
    """The drafting routine's own bearer secret. It can read the queue and
    submit drafts, nothing else; approving stays behind Daksh's sign-in."""
    expected = os.getenv("RISE_OUTREACH_TOKEN", "")
    supplied = (authorization or "")[7:].strip() if (authorization or "").startswith("Bearer ") else ""
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Routine credential required")


def _sent_ids() -> set[str]:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return {str(value) for value in state.get("sent_opportunity_ids", [])}
    except (OSError, ValueError):
        return set()


def _change_outreach(change: Any) -> Any:
    """Load, change and save outreach state under one lock, then commit the volume."""
    with _OUTREACH_LOCK:
        data = outreach_store.load(OUTREACH_PATH)
        try:
            result = change(data)
        except outreach_store.DraftError as exc:
            status = 404 if str(exc) == "unknown draft" else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        outreach_store.save(OUTREACH_PATH, data)
        COMMIT()
        return result


@app.get("/api/outreach/queue", dependencies=[Depends(require_routine)])
def outreach_queue() -> dict[str, Any]:
    run = _latest_live()
    data = outreach_store.load(OUTREACH_PATH)
    return {"run_id": run.get("run_id"), "leads": outreach_store.drafting_queue(run, data, _sent_ids())}


@app.post("/api/outreach/drafts", dependencies=[Depends(require_routine)])
def outreach_submit(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or "")
    if run_id != _latest_live().get("run_id"):
        raise HTTPException(status_code=409, detail="Drafts are for a run that is no longer the latest")
    drafts = payload.get("drafts")
    if not isinstance(drafts, list):
        raise HTTPException(status_code=400, detail="drafts must be a list")
    statuses = _change_outreach(lambda data: outreach_store.submit_drafts(data, run_id, drafts, _now()))
    return {"statuses": statuses}


@app.get("/api/outreach/drafts")
def outreach_list(claims: dict[str, Any] = Depends(require_daksh)) -> dict[str, Any]:
    del claims
    data = outreach_store.load(OUTREACH_PATH)
    now = _now()
    drafts = sorted(
        data["drafts"].values(),
        key=lambda draft: (str(draft.get("updated_at") or ""), draft["lead_id"]),
        reverse=True,
    )
    return {
        "now": now.isoformat(),
        "nextSlot": outreach_store.next_send_slot(now).isoformat(),
        "drafts": drafts,
    }


@app.patch("/api/outreach/drafts/{lead_id}")
def outreach_edit(
    lead_id: str, changes: dict[str, Any] = Body(...), claims: dict[str, Any] = Depends(require_daksh)
) -> dict[str, Any]:
    del claims
    return _change_outreach(lambda data: outreach_store.edit_draft(data, lead_id, changes, _now()))


@app.post("/api/outreach/drafts/{lead_id}/approve")
def outreach_approve(lead_id: str, claims: dict[str, Any] = Depends(require_daksh)) -> dict[str, Any]:
    del claims
    return _change_outreach(lambda data: outreach_store.approve(data, lead_id, _now()))


@app.post("/api/outreach/drafts/{lead_id}/reject")
def outreach_reject(lead_id: str, claims: dict[str, Any] = Depends(require_daksh)) -> dict[str, Any]:
    del claims
    return _change_outreach(lambda data: outreach_store.reject(data, lead_id, _now()))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "rise-personal-hunt"}


@app.get("/api/personal/latest")
def latest(response: Response, claims: dict[str, Any] = Depends(require_daksh)) -> dict[str, Any]:
    del claims
    run = _latest_live()
    response.headers["Cache-Control"] = "no-store"
    return {
        "run": {
            "id": run.get("run_id"),
            "date": run.get("run_date"),
            "status": run.get("status"),
            "completedAt": run.get("completed_at"),
            "rawCount": run.get("raw_count", 0),
            "eligibleCount": run.get("eligible_count", 0),
            "digestUsable": run.get("digest_usable", False),
        },
        "bengaluru": _sanitize(run.get("digest_primary", [])),
        "remote": _sanitize(run.get("digest_remote_fallback", [])),
        "needsVerification": _sanitize(run.get("needs_verification", [])),
        "withheldCount": sum(
            1
            for item in list(run.get("primary", [])) + list(run.get("remote_fallback", []))
            if not item.get("digest_approved")
        ),
        "funding": {
            "primary": _sanitize(run.get("funding_primary", [])),
            "extended": _sanitize(run.get("funding_extended", [])),
        },
        "sourceHealth": _sanitize(run.get("source_health", [])),
        "integrations": _sanitize(run.get("integrations", {})),
        "weeklyTargets": _sanitize(run.get("weeklyTargets", run.get("weekly_targets", []))),
        "sendQueue": _sanitize(run.get("send_queue", [])),
        "sendStreakDays": int(run.get("send_streak_days", 0) or 0),
        "costSummary": _sanitize(run.get("costSummary", run.get("cost_summary", {}))),
        "sourceYield": _sanitize(run.get("sourceYield", run.get("source_yield", {}))),
        "cacheStatistics": _sanitize(
            run.get("cacheStatistics", run.get("cache_statistics", run.get("cache_stats", {})))
        ),
        "apify": _apify_summary(),
    }

