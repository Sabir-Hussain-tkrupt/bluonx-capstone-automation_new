"""Business-clock helpers.

`date.today()` reads the server's local timezone, which is the wrong anchor for
scheduling decisions (a milestone "started today" must mean today in the business
timezone, not wherever the container happens to run). Every defaulted actual date
and — from Phase 10.3 — the daily check-in job resolve "today" through here so the
whole system shares one clock, configured by `settings.BUSINESS_TIMEZONE`.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def business_today() -> date:
    """Today's date in the configured business timezone (America/Chicago)."""
    return datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date()
