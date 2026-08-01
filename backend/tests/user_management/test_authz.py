"""Every admin endpoint rejects a project_manager with 403 via require_admin."""

from uuid import uuid4

import pytest

TARGET = str(uuid4())


@pytest.mark.parametrize(
    "method, path, json",
    [
        (
            "post",
            "/api/v1/users/invite",
            {"email": "new@bluonx.dev", "full_name": "New", "role": "project_manager"},
        ),
        ("get", "/api/v1/users", None),
        ("patch", f"/api/v1/users/{TARGET}", {"is_active": False}),
        ("delete", f"/api/v1/users/{TARGET}", None),
        ("post", f"/api/v1/users/{TARGET}/resend-invite", None),
    ],
)
def test_pm_is_forbidden(pm_client, method, path, json):
    tc = pm_client()
    resp = tc.request(method, path, json=json)
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()
