"""The write endpoints end to end, against the real database.

Covers the two rules the DB does NOT enforce (weekend, friendly duplicate) plus
the range path, whose whole reason for existing is atomicity.

The range tests require `fn_create_holiday_range` to be applied to the database.
Until the migration in database/migrations/ is run they will fail with a
PostgREST "function not found", which is the honest signal.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

# End-to-end write paths against the real database, as the module docstring says.
pytestmark = pytest.mark.requires_db

CREATE = "/api/v1/holidays"
RANGE = "/api/v1/holidays/range"


def _holiday(url_client, headers, payload):
    return url_client.post(CREATE, json=payload, headers=headers)


# ── Rules enforced in application code ──────────────────────────────────────


def test_weekend_is_rejected_with_the_calendar_wording(
    client, auth_headers, future_anchor
):
    """The DB permits a Saturday holiday; the API does not."""
    saturday = future_anchor + timedelta(days=5)

    resp = _holiday(
        client, auth_headers, {"holiday_date": saturday.isoformat(), "name": "Nope"}
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "Weekends are already non-working days, so adding one has no effect."
    )


def test_duplicate_returns_a_conflict_naming_the_date(
    client, auth_headers, future_anchor, holiday_sandbox
):
    """A bare 23505 names the index; the admin gets the date instead."""
    holiday_sandbox.add(future_anchor, "First")

    resp = _holiday(
        client,
        auth_headers,
        {"holiday_date": future_anchor.isoformat(), "name": "Second"},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == (
        f"{future_anchor.isoformat()} is already marked as a holiday."
    )


# ── Guardrail messages survive the round trip verbatim ──────────────────────


def test_contiguous_cap_message_reaches_the_client_intact(
    client, auth_headers, future_anchor, holiday_sandbox
):
    """A PT422 must arrive as a 422 carrying the DB's own words, not a generic
    500 or a canned 'submitted data was rejected'."""
    for offset in (0, 1, 2, 3, 4, 7, 8, 9, 10):
        holiday_sandbox.add(future_anchor + timedelta(days=offset), "Shutdown")

    friday = future_anchor + timedelta(days=11)
    resp = _holiday(
        client, auth_headers, {"holiday_date": friday.isoformat(), "name": "Shutdown"}
    )
    holiday_sandbox.track(friday)

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "16 day closure" in detail
    assert "max 14 consecutive non-working days" in detail


def test_past_date_message_reaches_the_client_intact(client, auth_headers):
    from app.core.time import business_today

    yesterday = business_today() - timedelta(days=1)
    resp = _holiday(
        client, auth_headers, {"holiday_date": yesterday.isoformat(), "name": "Past"}
    )

    assert resp.status_code == 422
    assert "past dates are frozen" in resp.json()["detail"]


# ── Update / delete ─────────────────────────────────────────────────────────


def test_update_renames_and_moves_a_holiday(
    client, auth_headers, future_anchor, holiday_sandbox
):
    row = holiday_sandbox.add(future_anchor, "Original")
    moved = future_anchor + timedelta(days=1)
    holiday_sandbox.track(moved)

    resp = client.patch(
        f"/api/v1/holidays/{row['id']}",
        json={"holiday_date": moved.isoformat(), "name": "Renamed"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["holiday_date"] == moved.isoformat()


def test_update_to_a_weekend_is_rejected(
    client, auth_headers, future_anchor, holiday_sandbox
):
    row = holiday_sandbox.add(future_anchor, "Original")
    saturday = future_anchor + timedelta(days=5)

    resp = client.patch(
        f"/api/v1/holidays/{row['id']}",
        json={"holiday_date": saturday.isoformat()},
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert "Weekends are already non-working days" in resp.json()["detail"]


def test_delete_removes_a_future_holiday(
    client, auth_headers, future_anchor, holiday_sandbox
):
    row = holiday_sandbox.add(future_anchor, "Removable")

    resp = client.delete(f"/api/v1/holidays/{row['id']}", headers=auth_headers)
    assert resp.status_code == 204


def test_delete_unknown_id_is_a_404(client, auth_headers):
    resp = client.delete(
        "/api/v1/holidays/99999999-9999-4999-8999-999999999999", headers=auth_headers
    )
    assert resp.status_code == 404


# ── Range: the atomicity case ───────────────────────────────────────────────


def test_range_inserts_weekdays_and_skips_weekends(
    client, auth_headers, future_anchor, holiday_sandbox
):
    """Sat through the following Sunday yields exactly the five weekdays."""
    start = future_anchor - timedelta(days=2)  # the Saturday before
    end = future_anchor + timedelta(days=6)  # the Sunday after
    for offset in range(-2, 7):
        holiday_sandbox.track(future_anchor + timedelta(days=offset))

    resp = client.post(
        RANGE,
        json={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "name": "Shutdown Week",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    rows = resp.json()
    assert [r["holiday_date"] for r in rows] == [
        (future_anchor + timedelta(days=n)).isoformat() for n in range(5)
    ]
    assert all(r["source"] == "manual" for r in rows)


def test_range_breaching_the_contiguous_cap_writes_nothing(
    client, auth_headers, future_anchor, holiday_sandbox, sb
):
    """THE atomicity test.

    A two-week Mon-Fri span is a 16-day closure. A multi-row INSERT would slip
    past the BEFORE-ROW trigger (it cannot see its own siblings) and write all
    ten rows; the RPC loops row-by-row, so the tenth trips the cap and the whole
    transaction rolls back.
    """
    start = future_anchor
    end = future_anchor + timedelta(days=11)  # week 2 Friday
    for offset in range(0, 12):
        holiday_sandbox.track(future_anchor + timedelta(days=offset))

    resp = client.post(
        RANGE,
        json={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "name": "Too Long",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 422, resp.text
    assert "consecutive non-working days" in resp.json()["detail"]

    # Nothing partially written.
    left = (
        sb.table("holidays")
        .select("holiday_date")
        .gte("holiday_date", start.isoformat())
        .lte("holiday_date", end.isoformat())
        .execute()
    )
    assert (left.data or []) == []


def test_range_over_an_existing_holiday_is_a_conflict(
    client, auth_headers, future_anchor, holiday_sandbox, sb
):
    """The clash names the date, and nothing else in the range is written."""
    clash = future_anchor + timedelta(days=2)
    holiday_sandbox.add(clash, "Already Here")
    for offset in range(0, 5):
        holiday_sandbox.track(future_anchor + timedelta(days=offset))

    resp = client.post(
        RANGE,
        json={
            "start_date": future_anchor.isoformat(),
            "end_date": (future_anchor + timedelta(days=4)).isoformat(),
            "name": "Overlaps",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert clash.isoformat() in resp.json()["detail"]

    remaining = (
        sb.table("holidays")
        .select("holiday_date")
        .gte("holiday_date", future_anchor.isoformat())
        .lte("holiday_date", (future_anchor + timedelta(days=4)).isoformat())
        .execute()
    )
    assert [r["holiday_date"] for r in (remaining.data or [])] == [clash.isoformat()]


def test_range_of_only_weekends_is_rejected(client, auth_headers, future_anchor):
    saturday = future_anchor + timedelta(days=5)
    sunday = future_anchor + timedelta(days=6)

    resp = client.post(
        RANGE,
        json={
            "start_date": saturday.isoformat(),
            "end_date": sunday.isoformat(),
            "name": "Weekend Only",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert "only weekends" in resp.json()["detail"]


def test_range_with_end_before_start_is_rejected(client, auth_headers, future_anchor):
    """Caught by the Pydantic model before any DB call."""
    resp = client.post(
        RANGE,
        json={
            "start_date": (future_anchor + timedelta(days=3)).isoformat(),
            "end_date": future_anchor.isoformat(),
            "name": "Backwards",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
