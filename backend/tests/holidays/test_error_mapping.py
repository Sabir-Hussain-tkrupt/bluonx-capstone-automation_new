"""SQLSTATE -> HTTP mapping for holiday writes, with no database.

The frontend's axios interceptor REPLACES the server message on 403/404/500 and
PRESERVES it on 409 and on a 422 whose detail is a string. That is why every
business rejection has to land on one of those two: a guardrail message routed
to any other status is silently swapped for boilerplate before an admin sees it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import holiday_service
from app.services.holiday_service import HolidayError
from tests.holidays.conftest import RecordingDB, make_api_error

FUTURE_MONDAY = date(2099, 6, 8)
FUTURE_SATURDAY = date(2099, 6, 13)
ADMIN = "11111111-1111-4111-8111-111111111111"


def _create(db, d=FUTURE_MONDAY):
    return holiday_service.create_holiday(
        holiday_date=d, name="Probe", created_by=ADMIN, db=db
    )


# ── PT422: the DB's own words, unchanged ────────────────────────────────────


def test_pt422_passes_the_db_message_through_verbatim():
    db_text = "Year 2027 already has 25 holidays (max 25). Remove one before adding another."
    db = RecordingDB(error=make_api_error("PT422", db_text))

    with pytest.raises(HolidayError) as exc:
        _create(db)

    assert exc.value.status_code == 422
    assert exc.value.detail == db_text


def test_pt409_passes_the_db_message_through_verbatim():
    db_text = "2099-06-10 is already marked as a holiday. Remove it first."
    db = RecordingDB(error=make_api_error("PT409", db_text))

    with pytest.raises(HolidayError) as exc:
        holiday_service.create_holiday_range(
            start_date=FUTURE_MONDAY,
            end_date=FUTURE_MONDAY,
            name="Probe",
            created_by=ADMIN,
            db=db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == db_text


# ── 23505: rewritten, because Postgres names the index ──────────────────────


def test_unique_violation_becomes_a_conflict_naming_the_date():
    db = RecordingDB(
        error=make_api_error(
            "23505", 'duplicate key value violates unique constraint "holidays_..."'
        )
    )

    with pytest.raises(HolidayError) as exc:
        _create(db)

    assert exc.value.status_code == 409
    assert exc.value.detail == "2099-06-08 is already marked as a holiday."


def test_unknown_error_becomes_a_generic_422():
    db = RecordingDB(error=make_api_error("42P01", "relation does not exist"))

    with pytest.raises(HolidayError) as exc:
        _create(db)

    assert exc.value.status_code == 422
    assert exc.value.detail == "The holiday could not be saved."


# ── The weekend gate is application code, and fires first ───────────────────


def test_weekend_is_rejected_without_touching_the_database():
    db = RecordingDB()

    with pytest.raises(HolidayError) as exc:
        _create(db, FUTURE_SATURDAY)

    assert exc.value.status_code == 422
    assert exc.value.detail == (
        "Weekends are already non-working days, so adding one has no effect."
    )
    assert db.inserts == [], "the weekend gate must short-circuit before the insert"


def test_update_to_a_weekend_is_rejected_without_touching_the_database():
    db = RecordingDB()

    with pytest.raises(HolidayError):
        holiday_service.update_holiday(
            holiday_id="x", changes={"holiday_date": FUTURE_SATURDAY}, db=db
        )

    assert db.inserts == []


def test_update_with_no_fields_is_a_400():
    with pytest.raises(HolidayError) as exc:
        holiday_service.update_holiday(holiday_id="x", changes={}, db=RecordingDB())

    assert exc.value.status_code == 400


# ── Not found ───────────────────────────────────────────────────────────────


def test_update_of_a_missing_row_is_a_404():
    with pytest.raises(HolidayError) as exc:
        holiday_service.update_holiday(
            holiday_id="x", changes={"name": "New"}, db=RecordingDB(rows=[])
        )

    assert exc.value.status_code == 404


def test_delete_of_a_missing_row_is_a_404():
    with pytest.raises(HolidayError) as exc:
        holiday_service.delete_holiday(holiday_id="x", db=RecordingDB(rows=[]))

    assert exc.value.status_code == 404


# ── Provenance is never client-supplied ─────────────────────────────────────


def test_create_forces_source_manual_and_the_authenticated_actor():
    db = RecordingDB()

    _create(db)

    assert db.inserts[0]["source"] == "manual"
    assert db.inserts[0]["created_by"] == ADMIN
