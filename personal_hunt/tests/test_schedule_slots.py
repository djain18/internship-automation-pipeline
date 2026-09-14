from datetime import datetime

import pytest

from schedule_slots import CRON, IST, SLOTS, job_for


@pytest.mark.parametrize(
    ("when", "job"),
    [
        ("2026-09-15T18:30:07", "collect"),
        ("2026-09-15T21:00:40", "deliver"),
        ("2026-09-15T10:00:05", "send"),  # Tuesday
        ("2026-09-19T10:00:05", None),  # Saturday: no sends
        ("2026-09-19T18:30:05", "collect"),  # Saturday still collects
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
