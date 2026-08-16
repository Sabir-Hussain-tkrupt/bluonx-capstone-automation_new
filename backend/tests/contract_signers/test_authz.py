"""Roster writes are admin-only; a project_manager gets 403 via require_admin.

There is deliberately no GET endpoint: both the settings page and the award
dropdown read contract_signers directly from Supabase, where
`contract_signers_select_authenticated` already permits any active user to read
all rows (including inactive ones). A FastAPI read would be a second read path.
"""

from uuid import uuid4

import pytest

TARGET = str(uuid4())


@pytest.mark.parametrize(
    "method, path, json",
    [
        (
            "post",
            "/api/v1/contract-signers",
            {"full_name": "Dana Reyes", "email": "dana@bluonx.dev", "title": "VP"},
        ),
        ("patch", f"/api/v1/contract-signers/{TARGET}", {"is_active": False}),
    ],
)
def test_pm_is_forbidden(pm_client, method, path, json):
    tc = pm_client()
    resp = tc.request(method, path, json=json)
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()


def test_there_is_no_get_endpoint(admin_client):
    """Reads go direct to Supabase under RLS. Adding a GET here would be a
    second read path for the same data."""
    tc = admin_client({"signers": []})
    assert tc.get("/api/v1/contract-signers").status_code == 405
