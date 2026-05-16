"""B.2 — POST /api/v1/bid-revision-requests/{id}/cancel."""

from __future__ import annotations

from .conftest import REVISION_REQUEST_ID, revision_row

URL = f"/api/v1/bid-revision-requests/{REVISION_REQUEST_ID}/cancel"


def test_200_cancels_pending(client_factory):
    spec = {
        "bid_revision_requests": {
            "select": [{"id": str(REVISION_REQUEST_ID), "status": "pending"}],
            "update": [revision_row(status="cancelled")],
        },
        "magic_link_tokens": {"update": []},
    }
    c = client_factory(spec)
    r = c.post(URL)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


def test_409_non_pending(client_factory):
    spec = {"bid_revision_requests": {
        "select": [{"id": str(REVISION_REQUEST_ID), "status": "submitted"}],
    }}
    c = client_factory(spec)
    assert c.post(URL).status_code == 409


def test_404_missing(client_factory):
    c = client_factory({"bid_revision_requests": {"select": []}})
    assert c.post(URL).status_code == 404


def test_409_toctou_zero_rows_updated(client_factory):
    # Pre-check sees pending, but the guarded UPDATE matches 0 rows (a
    # concurrent decline/finalize won the race).
    spec = {"bid_revision_requests": {
        "select": [{"id": str(REVISION_REQUEST_ID), "status": "pending"}],
        "update": [],
    }}
    c = client_factory(spec)
    assert c.post(URL).status_code == 409


def test_401_or_403_without_auth(client_factory):
    spec = {"bid_revision_requests": {
        "select": [{"id": str(REVISION_REQUEST_ID), "status": "pending"}],
        "update": [revision_row(status="cancelled")],
    }}
    c = client_factory(spec, auth=False)
    assert c.post(URL).status_code in (401, 403)
