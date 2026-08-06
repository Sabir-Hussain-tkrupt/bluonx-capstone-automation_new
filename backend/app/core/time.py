"""Business-clock helpers.

`date.today()` reads the server's local timezone, which is the wrong anchor for
scheduling decisions (a milestone "started today" must mean today in the business
timezone, not wherever the container happens to run). Every defaulted actual date
and the daily check-in job resolve "today" through here so the whole system
shares one clock, configured by `settings.BUSINESS_TIMEZONE`.

Working-day ARITHMETIC is not implemented here. It lives in the database —
`fn_is_business_day`, `fn_add_business_days`, `fn_business_days_between` (schema
section 6.13) — because it depends on the `holidays` table, and a second
implementation in Python would drift from it the first time either changed. The
`BusinessCalendar` class below is a transport and cache over those functions, not
a reimplementation of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def business_today() -> date:
    """Today's date in the configured business timezone (America/Chicago)."""
    return datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date()


@dataclass(frozen=True)
class Holiday:
    """One org-wide non-working day, as read from the `holidays` table."""

    date: date
    name: str


class BusinessCalendar:
    """Per-run façade over the SQL calendar functions.

    The database owns weekend and holiday arithmetic. This class only asks it
    questions and remembers the answers, so a batch that asks the same question
    for fifty rows pays for one round trip.

    Instantiate ONE per job run and let it die with the run. Never module-level:
    the memo must not outlive an admin editing the holiday calendar, and "today"
    is fixed for the life of an instance.
    """

    def __init__(self, db) -> None:
        self._db = db
        # Keyed on `sent` alone: `today` is fixed for a single run.
        self._since: dict[date, int] = {}
        self._added: dict[tuple[date, int], date] = {}
        self._primed: tuple[date, date] | None = None
        self._holidays: list[Holiday] = []

    def business_days_since(self, sent: date, today: date) -> int:
        """Working days elapsed in the half-open window (sent, today].

        Weekends and holidays both excluded. Delegates to
        `fn_business_days_between`.
        """
        if today <= sent:
            # Mirrors the SQL's own short-circuit; saves a pointless round trip.
            return 0

        cached = self._since.get(sent)
        if cached is None:
            resp = self._db.rpc(
                "fn_business_days_between",
                {"p_from": sent.isoformat(), "p_to": today.isoformat()},
            ).execute()
            cached = int(resp.data)
            self._since[sent] = cached
        return cached

    def add_business_days(self, start: date, days: int) -> date:
        """The date `days` working days after `start` — `fn_add_business_days`.

        Exact inverse of `business_days_since`.
        """
        key = (start, days)
        cached = self._added.get(key)
        if cached is None:
            resp = self._db.rpc(
                "fn_add_business_days",
                {"p_start": start.isoformat(), "p_days": days},
            ).execute()
            cached = date.fromisoformat(str(resp.data))
            self._added[key] = cached
        return cached

    def prime_holidays(self, start: date, end: date) -> None:
        """Load every holiday in [start, end] in ONE query.

        Call once per run, before any `holidays_in`. The guardrail trigger caps
        the table at 25 rows per year, so even a wide window is a handful of rows.
        """
        if end < start:
            self._holidays = []
            self._primed = (start, start)
            return

        resp = (
            self._db.table("holidays")
            .select("holiday_date, name")
            .gte("holiday_date", start.isoformat())
            .lte("holiday_date", end.isoformat())
            .order("holiday_date")
            .execute()
        )
        self._holidays = [
            Holiday(date.fromisoformat(str(r["holiday_date"])), str(r["name"]))
            for r in (resp.data or [])
        ]
        self._primed = (start, end)

    def holidays_in(self, start: date, end: date) -> list[Holiday]:
        """Holidays in the half-open window (start, end] — the same window
        `business_days_since` counts over, so the two always agree.

        A pure slice of the primed list, so this costs nothing per call. Raises
        when the window is not covered rather than returning a partial answer a
        caller would silently trust.
        """
        if self._primed is None:
            raise RuntimeError("holidays_in called before prime_holidays")
        primed_start, primed_end = self._primed
        if start < primed_start or end > primed_end:
            raise RuntimeError(
                f"holidays_in({start}, {end}) falls outside the primed range "
                f"({primed_start}, {primed_end})"
            )
        return [h for h in self._holidays if start < h.date <= end]
