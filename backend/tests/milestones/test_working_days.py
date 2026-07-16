"""working_days_since: weekday-only elapsed-day count (Phase 10.2)."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.time import WORKING_DAYS_SKIP_HOLIDAYS, working_days_since

# 2026-07-10 is a Friday.
FRI = date(2026, 7, 10)
SAT = date(2026, 7, 11)
SUN = date(2026, 7, 12)
MON = date(2026, 7, 13)
TUE = date(2026, 7, 14)
WED = date(2026, 7, 15)


@pytest.mark.parametrize(
    "sent,today,expected",
    [
        (FRI, FRI, 0),   # same day
        (FRI, SAT, 0),   # weekend does not count
        (FRI, SUN, 0),
        (FRI, MON, 1),
        (FRI, TUE, 2),
        (FRI, WED, 3),   # escalation fires here
        (MON, date(2026, 7, 16), 3),  # Mon -> Thu = 3 working days
        (WED, MON, 0),   # today before sent
    ],
)
def test_working_days_since(sent, today, expected):
    assert working_days_since(sent, today) == expected


def test_three_working_days_skips_a_weekend():
    """Friday-sent must not reach 3 working days until the following Wednesday."""
    assert working_days_since(FRI, TUE) < 3
    assert working_days_since(FRI, WED) == 3


def test_holidays_flag_is_off_for_mvp():
    assert WORKING_DAYS_SKIP_HOLIDAYS is False
