"""BusinessCalendar: the transport and cache over the SQL calendar functions.

The arithmetic itself is tested against the real database in
test_business_day_helpers.py. What is tested here is the part that is Python:
that the class asks the database the right question, asks it as few times as
possible, and refuses to answer from a window it has not loaded.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.time import BusinessCalendar

MON = date(2099, 6, 8)
TUE = date(2099, 6, 9)
WED = date(2099, 6, 10)
FRI = date(2099, 6, 12)


class SpyDB:
    """Records every rpc and table read, and replays canned answers."""

    def __init__(self, *, rpc_data=None, holiday_rows=None):
        self.rpc_data = rpc_data if rpc_data is not None else 3
        self.holiday_rows = holiday_rows or []
        self.rpc_calls: list[tuple[str, dict]] = []
        self.table_reads = 0

    def rpc(self, fn: str, params: dict):
        self.rpc_calls.append((fn, params))
        return _Deferred(self.rpc_data)

    def table(self, _name: str):
        self.table_reads += 1
        return self

    def select(self, *_a):
        return self

    def gte(self, *_a):
        return self

    def lte(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self.holiday_rows)


class _Result:
    def __init__(self, data):
        self.data = data


class _Deferred:
    """Mirrors the real client, where .rpc() is chainable and .execute() runs it."""

    def __init__(self, data):
        self._data = data

    def execute(self):
        return _Result(self._data)


# ── business_days_since ─────────────────────────────────────────────────────


def test_asks_the_database_with_the_half_open_window():
    db = SpyDB(rpc_data=3)
    cal = BusinessCalendar(db)

    assert cal.business_days_since(MON, FRI) == 3
    assert db.rpc_calls == [
        ("fn_business_days_between", {"p_from": "2099-06-08", "p_to": "2099-06-12"})
    ]


def test_backwards_window_short_circuits_without_a_round_trip():
    db = SpyDB()
    cal = BusinessCalendar(db)

    assert cal.business_days_since(WED, MON) == 0
    assert cal.business_days_since(MON, MON) == 0
    assert db.rpc_calls == []


def test_repeat_questions_cost_one_round_trip():
    """Alerts sent the same day are the common case in a sweep."""
    db = SpyDB(rpc_data=4)
    cal = BusinessCalendar(db)

    for _ in range(5):
        assert cal.business_days_since(MON, FRI) == 4

    assert len(db.rpc_calls) == 1


def test_distinct_send_dates_are_cached_separately():
    db = SpyDB(rpc_data=2)
    cal = BusinessCalendar(db)

    cal.business_days_since(MON, FRI)
    cal.business_days_since(TUE, FRI)
    cal.business_days_since(MON, FRI)

    assert len(db.rpc_calls) == 2


# ── add_business_days ───────────────────────────────────────────────────────


def test_add_business_days_parses_and_memoizes():
    db = SpyDB(rpc_data="2099-06-17")
    cal = BusinessCalendar(db)

    assert cal.add_business_days(MON, 3) == date(2099, 6, 17)
    assert cal.add_business_days(MON, 3) == date(2099, 6, 17)

    assert len(db.rpc_calls) == 1
    assert db.rpc_calls[0] == (
        "fn_add_business_days",
        {"p_start": "2099-06-08", "p_days": 3},
    )


# ── prime_holidays / holidays_in ────────────────────────────────────────────


def test_holidays_in_is_a_free_slice_of_one_query():
    db = SpyDB(
        holiday_rows=[
            {"holiday_date": "2099-06-08", "name": "On the boundary"},
            {"holiday_date": "2099-06-10", "name": "Inside"},
            {"holiday_date": "2099-06-12", "name": "On the far edge"},
        ]
    )
    cal = BusinessCalendar(db)
    cal.prime_holidays(MON, FRI)

    for _ in range(3):
        found = cal.holidays_in(MON, FRI)

    assert db.table_reads == 1
    # Half-open (start, end]: the row ON `start` is excluded, the one on `end` is
    # included — the same window fn_business_days_between counts over.
    assert [h.name for h in found] == ["Inside", "On the far edge"]


def test_holidays_in_before_priming_raises():
    cal = BusinessCalendar(SpyDB())

    with pytest.raises(RuntimeError, match="before prime_holidays"):
        cal.holidays_in(MON, FRI)


def test_holidays_in_outside_the_primed_range_raises():
    """Better to fail loudly than hand back a partial answer a caller trusts."""
    cal = BusinessCalendar(SpyDB())
    cal.prime_holidays(TUE, WED)

    with pytest.raises(RuntimeError, match="outside the primed range"):
        cal.holidays_in(MON, WED)

    with pytest.raises(RuntimeError, match="outside the primed range"):
        cal.holidays_in(TUE, FRI)


def test_priming_an_empty_window_is_safe():
    """min(sent_dates) can land after `today` if every alert is same-day."""
    cal = BusinessCalendar(SpyDB())
    cal.prime_holidays(FRI, MON)

    assert cal.holidays_in(FRI, FRI) == []
