"""GET /admin/docusign-health diagnostic (Task 9.3a).

Internal-auth only; returns ok on a successful mint, or the consent URL when
consent is missing. Mirrors the scheduler-health convention.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.main import app
from app.services.docusign_client import DocuSignConsentRequired, get_docusign_client

CONSENT_URL = "https://account-d.docusign.com/oauth/auth?response_type=code&x=1"


class _OkClient:
    async def get_access_token(self, force: bool = False) -> str:
        return "real-token"


class _ConsentClient:
    async def get_access_token(self, force: bool = False) -> str:
        raise DocuSignConsentRequired(consent_url=CONSENT_URL)


@pytest.fixture()
def authed_user() -> dict:
    return {"user_id": "u1", "email": "pm@example.com", "role": "project_manager", "is_active": True}


@pytest.fixture()
def client(authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_requires_auth():
    # No auth override → unauthenticated request is rejected.
    with TestClient(app) as c:
        resp = c.get("/api/v1/admin/docusign-health")
    assert resp.status_code in (401, 403)


def test_health_ok(client):
    app.dependency_overrides[get_docusign_client] = lambda: _OkClient()
    resp = client.get("/api/v1/admin/docusign-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True


def test_health_consent_required(client):
    app.dependency_overrides[get_docusign_client] = lambda: _ConsentClient()
    resp = client.get("/api/v1/admin/docusign-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["consent_required"] is True
    assert body["consent_url"] == CONSENT_URL
