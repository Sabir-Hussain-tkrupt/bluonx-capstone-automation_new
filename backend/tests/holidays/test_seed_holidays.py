"""The annual federal seed, against the real database.

The seed writes through the same guardrail trigger as everything else, so the
interesting assertions are about what it refuses to do: touch a row that already
exists, write a weekend, or write the past.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.time import business_today
from app.jobs.holiday_seed import years_to_seed
from app.services.holiday_service import _federal_candidates, seed_federal_holidays


@pytest.fixture()
def seed_year(sb) -> int:
    """A far-future year with no holidays in it, cleaned up afterwards."""
    year = business_today().year + 4

    existing = (
        sb.table("holidays")
        .select("id")
        .gte("holiday_date", date(year, 1, 1).isoformat())
        .lte("holiday_date", date(year, 12, 31).isoformat())
        .limit(1)
        .execute()
    )
    assert not (existing.data or []), f"{year} is not empty; pick a further-out year"

    try:
        yield year
    finally:
        sb.table("holidays").delete().gte(
            "holiday_date", date(year, 1, 1).isoformat()
        ).lte("holiday_date", date(year, 12, 31).isoformat()).execute()


# ── Candidate selection (pure, no DB) ───────────────────────────────────────


def test_candidates_are_federal_weekdays_only():
    """observed=True makes the library emit both the statutory date and its
    observed weekday when the statutory one is a weekend. Dropping weekends
    resolves that to the day the office is actually shut."""
    candidates = _federal_candidates([2026, 2027])

    assert candidates, "expected federal holidays"
    assert all(d.weekday() < 5 for d, _ in candidates)
    assert len({d for d, _ in candidates}) == len(candidates), "dates must be unique"

    dates = {d for d, _ in candidates}
    # 2026: Jul 4 is a Saturday, so the office shuts Friday Jul 3.
    assert date(2026, 7, 3) in dates
    assert date(2026, 7, 4) not in dates


def test_candidate_names_fit_the_column():
    for _, name in _federal_candidates([2026, 2027]):
        assert 0 < len(name) <= 100
        assert name == name.strip()


def test_no_state_subdivision_is_applied():
    """Federal only. Missouri statutory days are state-government closures a
    private construction firm does not observe."""
    names = {n for _, n in _federal_candidates([2026])}
    assert not any("Truman" in n for n in names)


# ── Seeding against the real table ──────────────────────────────────────────


@pytest.mark.requires_db
def test_seed_writes_federal_weekdays_with_no_actor(sb, seed_year):
    result = seed_federal_holidays(sb, years=[seed_year])

    assert result["inserted"] > 0
    assert result["rejected"] == []

    rows = (
        sb.table("holidays")
        .select("holiday_date, name, source, created_by")
        .gte("holiday_date", date(seed_year, 1, 1).isoformat())
        .lte("holiday_date", date(seed_year, 12, 31).isoformat())
        .execute()
    ).data

    assert len(rows) == result["inserted"]
    assert all(r["source"] == "seeded" for r in rows)
    assert all(r["created_by"] is None for r in rows), "seeded rows have no human actor"
    assert all(date.fromisoformat(r["holiday_date"]).weekday() < 5 for r in rows)


@pytest.mark.requires_db
def test_seed_is_idempotent(sb, seed_year):
    first = seed_federal_holidays(sb, years=[seed_year])
    second = seed_federal_holidays(sb, years=[seed_year])

    assert second["inserted"] == 0
    assert second["skipped_existing"] == first["inserted"]


@pytest.mark.requires_db
def test_seed_never_touches_a_manual_row(sb, seed_year):
    """An admin who renamed a federal holiday, or claimed the date for their own,
    must keep their row when the seed runs."""
    target, _ = _federal_candidates([seed_year])[0]
    sb.table("holidays").insert(
        {
            "holiday_date": target.isoformat(),
            "name": "Our Own Name For It",
            "source": "manual",
        }
    ).execute()

    seed_federal_holidays(sb, years=[seed_year])

    row = (
        sb.table("holidays")
        .select("name, source")
        .eq("holiday_date", target.isoformat())
        .single()
        .execute()
    ).data
    assert row["source"] == "manual"
    assert row["name"] == "Our Own Name For It"


def test_seed_skips_past_dates(sb):
    """The guardrail freezes the past, so the seed must filter rather than fail."""
    last_year = business_today().year - 1

    result = seed_federal_holidays(sb, years=[last_year])

    assert result["inserted"] == 0
    assert result["skipped_past"] > 0
    assert result["rejected"] == []


# ── Which years the annual job picks ────────────────────────────────────────


class _YearSpyDB:
    def __init__(self, has_seeded_rows: bool):
        self._rows = [{"id": "x"}] if has_seeded_rows else []

    def table(self, _n):
        return self

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def gte(self, *_a):
        return self

    def lte(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


def test_job_seeds_next_year_only_when_this_year_is_already_done():
    today = date(2026, 1, 2)
    assert years_to_seed(_YearSpyDB(True), today) == [2027]


def test_job_recovers_a_year_that_was_never_seeded():
    """The escape hatch for the app being down on January 2 — far worse than a
    resurrected holiday."""
    today = date(2026, 1, 2)
    assert years_to_seed(_YearSpyDB(False), today) == [2026, 2027]
