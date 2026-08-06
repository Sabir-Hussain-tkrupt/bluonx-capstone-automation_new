"""The three SQL business-day functions, exercised against the real database.

These are deliberately NOT mocked. The logic lives entirely in Postgres
(fn_is_business_day / fn_add_business_days / fn_business_days_between reading the
holidays table), so a Python double would assert nothing about the thing that
actually decides whether a vendor gets flagged.

`future_anchor` is a Monday, so within a week:
    anchor+0 Mon  +1 Tue  +2 Wed  +3 Thu  +4 Fri  +5 Sat  +6 Sun
"""

from __future__ import annotations

from datetime import timedelta

import pytest


def _between(sb, d_from, d_to) -> int:
    resp = sb.rpc(
        "fn_business_days_between",
        {"p_from": d_from.isoformat(), "p_to": d_to.isoformat()},
    ).execute()
    return int(resp.data)


def _add(sb, start, days):
    from datetime import date

    resp = sb.rpc(
        "fn_add_business_days", {"p_start": start.isoformat(), "p_days": days}
    ).execute()
    return date.fromisoformat(str(resp.data))


def _is_business_day(sb, d) -> bool:
    resp = sb.rpc("fn_is_business_day", {"p_date": d.isoformat()}).execute()
    return bool(resp.data)


# ── The canonical case ──────────────────────────────────────────────────────


def test_friday_to_wednesday_is_three_working_days(sb, future_anchor):
    """A check-in sent Friday is due end of the following Wednesday.

    This is the rule the whole feature exists to enforce, stated in the brief.
    """
    friday = future_anchor + timedelta(days=4)
    saturday = friday + timedelta(days=1)
    sunday = friday + timedelta(days=2)
    monday = friday + timedelta(days=3)
    tuesday = friday + timedelta(days=4)
    wednesday = friday + timedelta(days=5)

    assert _between(sb, friday, saturday) == 0
    assert _between(sb, friday, sunday) == 0
    assert _between(sb, friday, monday) == 1
    assert _between(sb, friday, tuesday) == 2
    assert _between(sb, friday, wednesday) == 3

    # And the forward direction agrees: 3 working days after Friday IS Wednesday.
    assert _add(sb, friday, 3) == wednesday


def test_zero_and_backwards_windows(sb, future_anchor):
    """`p_to <= p_from` is 0, not a negative or an error."""
    assert _between(sb, future_anchor, future_anchor) == 0
    assert _between(sb, future_anchor, future_anchor - timedelta(days=3)) == 0


# ── Holidays ────────────────────────────────────────────────────────────────


def test_holiday_inside_the_window_extends_the_deadline(
    sb, future_anchor, holiday_sandbox
):
    """A holiday mid-window is not counted, so the reply-by date slips a day."""
    friday = future_anchor + timedelta(days=4)
    monday = friday + timedelta(days=3)
    wednesday = friday + timedelta(days=5)
    thursday = friday + timedelta(days=6)

    # Baseline first, so the delta is attributable to the holiday alone.
    assert _between(sb, friday, wednesday) == 3

    holiday_sandbox.add(monday, "Planted Monday Holiday")

    assert _is_business_day(sb, monday) is False
    assert _between(sb, friday, wednesday) == 2
    assert _add(sb, friday, 3) == thursday


def test_holiday_adjacent_to_a_weekend(sb, future_anchor, holiday_sandbox):
    """A Friday holiday merges with the weekend into a four-day closure."""
    friday = future_anchor + timedelta(days=4)
    thursday = future_anchor + timedelta(days=3)
    next_monday = future_anchor + timedelta(days=7)

    holiday_sandbox.add(friday, "Planted Friday Holiday")

    assert _is_business_day(sb, friday) is False
    # One working day after Thursday skips Fri/Sat/Sun and lands on Monday.
    assert _add(sb, thursday, 1) == next_monday
    assert _between(sb, thursday, next_monday) == 1


def test_weekend_is_never_a_business_day(sb, future_anchor):
    """Hardcoded in the DB by design — no holiday row required."""
    assert _is_business_day(sb, future_anchor) is True
    assert _is_business_day(sb, future_anchor + timedelta(days=5)) is False  # Sat
    assert _is_business_day(sb, future_anchor + timedelta(days=6)) is False  # Sun


# ── The inverse property ────────────────────────────────────────────────────


@pytest.mark.parametrize("n", range(1, 11))
def test_between_inverts_add(sb, future_anchor, n):
    """fn_business_days_between(d, fn_add_business_days(d, n)) == n."""
    assert _between(sb, future_anchor, _add(sb, future_anchor, n)) == n


@pytest.mark.parametrize("n", range(1, 11))
def test_between_inverts_add_across_a_holiday(sb, future_anchor, holiday_sandbox, n):
    """The property must hold with a holiday planted mid-span, not just on a
    clean calendar — that is where an off-by-one between the two would hide."""
    holiday_sandbox.add(future_anchor + timedelta(days=2), "Planted Wednesday")
    assert _between(sb, future_anchor, _add(sb, future_anchor, n)) == n


def test_negative_offset_is_rejected(sb, future_anchor):
    """fn_add_business_days has no negative branch; it raises PT422."""
    from postgrest.exceptions import APIError

    with pytest.raises(APIError) as exc:
        _add(sb, future_anchor, -1)
    assert "PT422" in str(exc.value)
