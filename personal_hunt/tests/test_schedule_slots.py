from datetime import datetime

import pytest

from schedule_slots import CRON, IST, SLOTS, job_for


@pytest.mark.parametrize(
    ("when", "job"),
    [
        ("2026-09-16T06:30:04", "collect"),  # 2026-09-16: collect moved to 06:30
        ("2026-09-16T08:30:04", "deliver"),
        ("2026-09-19T08:30:04", "deliver"),  # Saturday still gets the morning digest
        ("2026-09-15T08:00:02", None),
        ("2026-09-15T06:00:02", None),  # the 06:00 firing of the same cron is idle
        ("2026-09-15T18:30:07", None),  # the old evening collect slot is gone
        ("2026-09-15T21:00:40", "deliver"),
        ("2026-09-15T10:00:05", "send"),  # Tuesday
        ("2026-09-19T10:00:05", None),  # Saturday: no sends
        ("2026-09-19T06:30:05", "collect"),  # Saturday still collects
        ("2026-09-19T21:00:05", "deliver"),  # and still gets the review email
        ("2026-09-15T18:00:03", None),
        ("2026-09-15T21:30:02", None),
        ("2026-09-15T10:30:02", None),
    ],
)
def test_job_for(when, job) -> None:
    assert job_for(datetime.fromisoformat(when).replace(tzinfo=IST)) == job


def test_cron_fires_at_every_slot() -> None:
    minutes, hours = CRON.split()[:2]
    for hour, minute in SLOTS:
        assert str(minute) in minutes.split(",") and str(hour) in hours.split(",")


def test_collect_lands_before_the_morning_digest() -> None:
    """The 08:30 digest must render a collect from the same morning, not a
    stale one: that is the whole point of the 2026-09-16 move."""
    collect_hour, collect_minute = next(at for at, job in SLOTS.items() if job == "collect")
    assert (collect_hour, collect_minute) < (8, 30)


def test_exactly_one_collect_per_day() -> None:
    """Apify is capped at $33/month with a $0.70 per-run ceiling; a second
    daily collect would hard-stop the paid source mid-month."""
    assert sum(1 for job in SLOTS.values() if job == "collect") == 1
