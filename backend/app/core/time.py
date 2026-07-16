"""Business-clock helpers.

`date.today()` reads the server's local timezone, which is the wrong anchor for
scheduling decisions (a milestone "started today" must mean today in the business
timezone, not wherever the container happens to run). Every defaulted actual date
and — from Phase 10.3 — the daily check-in job resolve "today" through here so the
whole system shares one clock, configured by `settings.BUSINESS_TIMEZONE`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

# TODO(reconsider): weekends-only for now (client-confirmed). Holidays are NOT
# accounted for. Revisit with a configurable US holiday calendar if the client
# needs federal/observed holidays excluded from the 3-working-day window.
# See docs/DEFERRED.md.
WORKING_DAYS_SKIP_HOLIDAYS = False


def business_today() -> date:
    """Today's date in the configured business timezone (America/Chicago)."""
    return datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date()


def working_days_since(sent: date, today: date) -> int:
    """Count working days (Mon–Fri) strictly after `sent`, up to and including `today`.

    Used by the milestone no-response escalation to require 3 WORKING days of
    silence before escalating, so a Friday check-in is not treated as overdue on
    Monday. Weekends are skipped; holidays are NOT (see WORKING_DAYS_SKIP_HOLIDAYS).

    Examples (Fri = weekday 4, Sat = 5, Sun = 6):
      Fri → Sat = 0, Fri → Sun = 0, Fri → Mon = 1, Fri → Tue = 2, Fri → Wed = 3.
      Mon → Thu = 3.
    Returns 0 when `today <= sent`.
    """
    if today <= sent:
        return 0
    count = 0
    cursor = sent + timedelta(days=1)
    while cursor <= today:
        if cursor.weekday() < 5:  # Mon–Fri
            count += 1
        cursor += timedelta(days=1)
    return count
