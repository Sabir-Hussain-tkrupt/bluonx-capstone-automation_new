"""Every holiday write endpoint rejects a project_manager with 403.

This is the real gate. The endpoints hold the service_role key, which bypasses
RLS entirely, so the holidays_*_admin policies do not defend this path and the
/settings/calendar route guard is cosmetic. If require_admin ever came off one of
these handlers, a PM could edit the org calendar by calling the API directly and
nothing else in the stack would stop them.
"""

from __future__ import annotations

import pytest

HOLIDAY_ID = "33333333-3333-4333-8333-333333333333"


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("post", "/api/v1/holidays", {"holiday_date": "2099-06-10", "name": "X"}),
        (
            "post",
            "/api/v1/holidays/range",
            {"start_date": "2099-06-10", "end_date": "2099-06-11", "name": "X"},
        ),
        ("patch", f"/api/v1/holidays/{HOLIDAY_ID}", {"name": "X"}),
        ("delete", f"/api/v1/holidays/{HOLIDAY_ID}", None),
    ],
)
def test_project_manager_is_forbidden(pm_client, method, path, body):
    tc = pm_client()

    resp = tc.request(method, path, json=body)

    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()


def test_forbidden_before_any_db_write(pm_client):
    """The 403 short-circuits — a rejected request must not touch the table."""
    from tests.holidays.conftest import RecordingDB

    db = RecordingDB()
    tc = pm_client(db)

    tc.post("/api/v1/holidays", json={"holiday_date": "2099-06-10", "name": "X"})

    assert db.inserts == []
    assert db.rpc_calls == []
