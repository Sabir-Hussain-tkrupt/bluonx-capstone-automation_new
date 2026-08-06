"""
Annual federal-holiday top-up.

The vendor responsiveness clock counts working days against the `holidays`
table. If that table runs dry, the clock silently reverts to weekends-only and
nobody notices — vendors just start getting flagged a day early over Christmas.
This job keeps the calendar at least twelve months ahead without anyone
remembering to do it.

Federal holidays only, `observed=True`, no state subdivision: the client is in
Missouri, and Missouri statutory days are state-government closures a private
construction firm does not observe.

KNOWN WART: a seeded holiday an admin deletes from year N+1 *before* the January
run that first seeds N+1 will be re-added by that run. Suppressing it properly
needs a tombstone or an `is_suppressed` column — a schema change, out of scope
here. `_years_to_seed` keeps the window as small as it can be.

See backend/app/jobs/README.md for the job contract.
"""

from __future__ import annotations

import logging
from datetime import date

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.core.time import business_today
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services.holiday_service import seed_federal_holidays

logger = logging.getLogger(__name__)

JOB_ID = "holiday_seed"


def years_to_seed(db, today: date) -> list[int]:
    """Next year always; the current year only if it was never seeded.

    Seeding next year is the whole point — it keeps the calendar twelve months
    ahead. NOT re-seeding the current year unconditionally is deliberate: an
    admin who deleted a seeded holiday because the firm works that day must not
    have it silently resurrected every January.

    The never-seeded escape hatch covers the worse failure — the app being down
    on January 2, leaving a whole year with no holiday awareness at all.
    """
    years = [today.year + 1]

    seeded_this_year = (
        db.table("holidays")
        .select("id")
        .eq("source", "seeded")
        .gte("holiday_date", date(today.year, 1, 1).isoformat())
        .lte("holiday_date", date(today.year, 12, 31).isoformat())
        .limit(1)
        .execute()
    )
    if not (seeded_this_year.data or []):
        years.insert(0, today.year)

    return years


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    today = business_today()
    return seed_federal_holidays(db, years=years_to_seed(db, today), today=today)


def register(scheduler) -> None:
    """Register the annual holiday seed.

    15:00 UTC on January 2 = 09:00 America/Chicago (CST, UTC-6 in January).

    January 2 rather than January 1: New Year's Day is itself a holiday, and by
    the time the job would run on the 1st that date is already past and frozen by
    the guardrail trigger.

    Deliberately absent from scheduler_self_check.EXPECTED_INTERVALS — a one-year
    cadence is meaningless to staleness math.
    """
    scheduler.add_job(
        _run,
        CronTrigger(month=1, day=2, hour=15, minute=0),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (annually on January 2 at 15:00 UTC)", JOB_ID)
