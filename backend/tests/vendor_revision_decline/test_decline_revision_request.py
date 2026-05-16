"""B.5 — GET /api/v1/vendor-portal/revision-requests/{id}/decline?token=..."""

from __future__ import annotations

from uuid import uuid4

from .conftest import RAW_TOKEN, REVISION_REQUEST_ID, _past, token_row

BASE = f"/api/v1/vendor-portal/revision-requests/{REVISION_REQUEST_ID}/decline"
URL = f"{BASE}?token={RAW_TOKEN}"


def _pending_spec(**over) -> dict:
    spec = {
        "magic_link_tokens": {"select": [token_row()], "update": []},
        "bid_revision_requests": {
            "select": [{"id": str(REVISION_REQUEST_ID), "status": "pending"}],
            "update": [{"id": str(REVISION_REQUEST_ID), "status": "declined"}],
        },
    }
    spec.update(over)
    return spec


def test_200_html_on_valid_decline(client_factory):
    c = client_factory(_pending_spec())
    r = c.get(URL)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert "declined" in r.text.lower()


def test_403_token_id_mismatch(client_factory):
    spec = _pending_spec(magic_link_tokens={
        "select": [token_row(bid_revision_request_id=str(uuid4()))],
        "update": [],
    })
    c = client_factory(spec)
    r = c.get(URL)
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("text/html")


def test_410_non_pending(client_factory):
    spec = _pending_spec(bid_revision_requests={
        "select": [{"id": str(REVISION_REQUEST_ID), "status": "submitted"}],
    })
    c = client_factory(spec)
    assert c.get(URL).status_code == 410


def test_410_toctou_zero_rows(client_factory):
    spec = _pending_spec(bid_revision_requests={
        "select": [{"id": str(REVISION_REQUEST_ID), "status": "pending"}],
        "update": [],
    })
    c = client_factory(spec)
    assert c.get(URL).status_code == 410


def test_410_revoked_token(client_factory):
    spec = _pending_spec(magic_link_tokens={
        "select": [token_row(revoked_at="2025-01-01T00:00:00+00:00")],
    })
    c = client_factory(spec)
    assert c.get(URL).status_code == 410


def test_410_expired_token(client_factory):
    spec = _pending_spec(magic_link_tokens={
        "select": [token_row(expires_at=_past())],
    })
    c = client_factory(spec)
    assert c.get(URL).status_code == 410


def test_404_unknown_token(client_factory):
    spec = _pending_spec(magic_link_tokens={"select": []})
    c = client_factory(spec)
    r = c.get(URL)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("text/html")


def test_422_missing_token_param(client_factory):
    c = client_factory(_pending_spec())
    assert c.get(BASE).status_code == 422
