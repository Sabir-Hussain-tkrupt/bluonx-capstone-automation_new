"""The three DB guardrails, against the real database.

Past dates frozen, 25 holidays per calendar year, 14 consecutive non-working
days. All three raise SQLSTATE PT422 with a message written for a human; the
service passes that message through verbatim, so these tests assert on the text
the admin actually sees.

KNOWN COVERAGE GAP: the guardrail's "delete a past holiday" and "update a row
whose OLD date is past" branches are unreachable from a test. A past-dated row
cannot be created in the first place (the INSERT guard fires first), and
disabling the trigger to plant one needs table-owner rights. The frozen-past
intent is covered here through the INSERT path only.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from postgrest.exceptions import APIError

from app.core.time import business_today

# The guardrails under test are DB triggers, so every test here needs the real
# database.
pytestmark = pytest.mark.requires_db


def _insert(sb, d: date, name: str = "Guardrail Probe"):
    return (
        sb.table("holidays")
        .insert({"holiday_date": d.isoformat(), "name": name, "source": "manual"})
        .execute()
    )


# ── 1. Past dates are frozen ────────────────────────────────────────────────


def test_past_date_insert_is_rejected(sb):
    yesterday = business_today() - timedelta(days=1)

    with pytest.raises(APIError) as exc:
        _insert(sb, yesterday, "Yesterday")

    message = str(exc.value)
    assert "PT422" in message
    assert "past dates are frozen" in message


# ── 2. 25 holidays per calendar year ────────────────────────────────────────


def test_year_cap_rejects_the_twenty_sixth(sb, holiday_sandbox):
    """Fill a far-future year to exactly 25, then prove the 26th bounces.

    The target year is computed from what is already there rather than assumed
    empty, so the test stays correct once the annual seed has run.
    """
    year = business_today().year + 3

    existing = (
        sb.table("holidays")
        .select("holiday_date")
        .gte("holiday_date", date(year, 1, 1).isoformat())
        .lte("holiday_date", date(year, 12, 31).isoformat())
        .execute()
    )
    already = len(existing.data or [])
    assert already < 25, f"{year} is already full; pick a further-out year"

    # Spread across the year on Wednesdays, so no two rows are adjacent and the
    # contiguous-run cap never interferes with the count cap under test.
    cursor = date(year, 1, 1)
    cursor += timedelta(days=(2 - cursor.weekday()) % 7)  # first Wednesday
    taken = {str(r["holiday_date"]) for r in (existing.data or [])}

    planted = 0
    while planted < 25 - already:
        if cursor.isoformat() not in taken:
            holiday_sandbox.add(cursor, f"Filler {planted}")
            planted += 1
        cursor += timedelta(days=14)

    with pytest.raises(APIError) as exc:
        _insert(sb, cursor, "One Too Many")
    holiday_sandbox.track(cursor)  # in case a regression lets it through

    message = str(exc.value)
    assert "PT422" in message
    assert "max 25" in message


# ── 3. 14 consecutive non-working days ──────────────────────────────────────


def test_contiguous_cap_rejects_a_run_over_fourteen(sb, future_anchor, holiday_sandbox):
    """A two-week Mon-Fri shutdown is a 16-day closure once weekends are counted.

    Nine rows (week 1 Mon-Fri, week 2 Mon-Thu) sit at 13 days and are accepted.
    Week 2's Friday extends the run to the following Sunday and the preceding
    Saturday: 2 + 5 + 2 + 5 + 2 = 16, over the cap.
    """
    for offset in (0, 1, 2, 3, 4, 7, 8, 9, 10):
        holiday_sandbox.add(future_anchor + timedelta(days=offset), "Shutdown")

    week_two_friday = future_anchor + timedelta(days=11)
    with pytest.raises(APIError) as exc:
        _insert(sb, week_two_friday, "Shutdown")
    holiday_sandbox.track(week_two_friday)

    message = str(exc.value)
    assert "PT422" in message
    assert "consecutive non-working days" in message
    assert "16 day closure" in message


def test_thirteen_day_run_is_accepted(sb, future_anchor, holiday_sandbox):
    """The cap is 14, not 9 — the boundary must let a real shutdown week through."""
    for offset in (0, 1, 2, 3, 4, 7, 8, 9, 10):
        holiday_sandbox.add(future_anchor + timedelta(days=offset), "Shutdown")

    rows = (
        sb.table("holidays")
        .select("holiday_date")
        .gte("holiday_date", future_anchor.isoformat())
        .lte("holiday_date", (future_anchor + timedelta(days=10)).isoformat())
        .execute()
    )
    assert len(rows.data or []) == 9


# ── Deleting a future holiday is allowed ────────────────────────────────────


def test_future_holiday_can_be_deleted(sb, future_anchor, holiday_sandbox):
    row = holiday_sandbox.add(future_anchor, "Removable")

    sb.table("holidays").delete().eq("id", row["id"]).execute()

    gone = (
        sb.table("holidays")
        .select("id")
        .eq("holiday_date", future_anchor.isoformat())
        .execute()
    )
    assert not (gone.data or [])
