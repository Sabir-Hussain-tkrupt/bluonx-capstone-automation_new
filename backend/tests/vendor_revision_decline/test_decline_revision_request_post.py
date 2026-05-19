"""B.5 — POST /api/v1/vendor-portal/revision-requests/{id}/decline.

SPA-mediated decline: vendor JWT in the Authorization header, optional
decline_reason in the JSON body, JSON response (BidRevisionRequestResponse).
"""

from __future__ import annotations

from .conftest import (
    BASE,
    OTHER_REVISION_REQUEST_ID,
    REVISION_REQUEST_ID,
    revision_request_row,
    vendor_ctx,
)

AUTH = {"Authorization": "Bearer test-vendor-token"}


def _spec(*, select, update) -> dict:
    return {
        "bid_revision_requests": {"select": select, "update": update},
        "magic_link_tokens": {"update": []},
    }


def test_200_with_decline_reason(client_factory):
    row = revision_request_row(status="declined", decline_reason="Capacity full")
    c = client_factory(
        _spec(select=[row], update=[row]), ctx=vendor_ctx()
    )
    r = c.post(BASE, json={"decline_reason": "Capacity full"}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "declined"
    assert body["decline_reason"] == "Capacity full"
    assert body["id"] == str(REVISION_REQUEST_ID)


def test_200_without_reason_field_stores_null(client_factory):
    row = revision_request_row(status="declined", decline_reason=None)
    c = client_factory(_spec(select=[row], update=[row]), ctx=vendor_ctx())
    r = c.post(BASE, json={}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["decline_reason"] is None


def test_200_blank_reason_normalized_to_null(client_factory):
    row = revision_request_row(status="declined", decline_reason=None)
    c = client_factory(_spec(select=[row], update=[row]), ctx=vendor_ctx())
    r = c.post(BASE, json={"decline_reason": "   "}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["decline_reason"] is None


def test_403_initial_bid_jwt_has_no_revision_claim(client_factory):
    c = client_factory(
        _spec(select=[], update=[]), ctx=vendor_ctx(with_revision=False)
    )
    r = c.post(BASE, json={}, headers=AUTH)
    assert r.status_code == 403, r.text


def test_403_jwt_claim_does_not_match_path_id(client_factory):
    c = client_factory(
        _spec(select=[], update=[]),
        ctx=vendor_ctx(revision_request_id=OTHER_REVISION_REQUEST_ID),
    )
    r = c.post(BASE, json={}, headers=AUTH)
    assert r.status_code == 403, r.text


def test_410_when_request_not_pending(client_factory):
    # Exists, but the guarded update matches zero rows (already terminal).
    c = client_factory(
        _spec(select=[revision_request_row()], update=[]), ctx=vendor_ctx()
    )
    r = c.post(BASE, json={}, headers=AUTH)
    assert r.status_code == 410, r.text


def test_404_when_request_unknown(client_factory):
    c = client_factory(_spec(select=[], update=[]), ctx=vendor_ctx())
    r = c.post(BASE, json={}, headers=AUTH)
    assert r.status_code == 404, r.text


def test_401_when_no_jwt(client_factory):
    # No get_vendor_context override → real bearer dependency runs.
    c = client_factory(_spec(select=[], update=[]), ctx=None)
    r = c.post(BASE, json={})
    assert r.status_code in (401, 403), r.text
