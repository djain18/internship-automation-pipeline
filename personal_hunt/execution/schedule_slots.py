"""Which job a firing of the one Modal cron should run.

The Modal workspace plan allows 5 scheduled functions in total and 4 are
used by other apps (deploy error 2026-09-14), so this app keeps a single
cron and dispatches here by IST wall-clock time.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
# (hour, minute) -> job. Weekday-only jobs are listed in WEEKDAY_ONLY.
# 2026-09-14 timeline (approved-outreach plan): collect 18:30, the drafting
# routine runs after it, the review email (digest + drafts) at 21:00, approvals
# lock 09:00, approved emails send 10:00 Mon-Fri.
SLOTS = {(18, 30): "collect", (21, 0): "deliver", (10, 0): "send"}
WEEKDAY_ONLY = {"send"}
CRON = "0,30 10,18,21 * * *"


def job_for(now: datetime) -> str | None:
    local = now.astimezone(IST)
    job = SLOTS.get((local.hour, 0 if local.minute < 30 else 30))
    if job in WEEKDAY_ONLY and local.weekday() >= 5:
        return None
    return job
