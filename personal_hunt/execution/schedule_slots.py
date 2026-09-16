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
# 2026-09-15: Daksh wants the 08:30 digest every day as well.
# 2026-09-16: collect moved 18:30 -> 06:30. The 08:30 digest was re-rendering a
# 14-hour-old collect whose leads were already in sent_opportunity_ids, so it
# read "no new internship matches" on a working pipeline. Daksh reviews in the
# morning and wants outreach out by 11:00, so the day now runs
# collect 06:30 -> drafting routine ~07:15 -> review email 08:30 -> approvals
# lock 09:00 -> send 10:00. The 21:00 deliver stays as a catch-up delivery.
# Still ONE collect per day: sources.yml caps Apify at $33/month with a $0.70
# per-run ceiling, and two collects a day (~60 runs) would hard-stop mid-month.
SLOTS = {(6, 30): "collect", (8, 30): "deliver", (21, 0): "deliver", (10, 0): "send"}
WEEKDAY_ONLY = {"send"}
CRON = "0,30 6,8,10,21 * * *"


def job_for(now: datetime) -> str | None:
    local = now.astimezone(IST)
    job = SLOTS.get((local.hour, 0 if local.minute < 30 else 30))
    if job in WEEKDAY_ONLY and local.weekday() >= 5:
        return None
    return job
