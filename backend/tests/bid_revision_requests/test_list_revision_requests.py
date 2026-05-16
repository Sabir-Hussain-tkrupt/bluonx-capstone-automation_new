"""B.3 — GET /api/v1/bid-revision-requests?bid_package_id=..."""

from __future__ import annotations

from .conftest import BID_PACKAGE_ID, INVITATION_ID, revision_row

URL = f"/api/v1/bid-revision-requests?bid_package_id={BID_PACKAGE_ID}"


def test_200_lists_for_package(client_factory):
    spec = {
        "bid_invitations": {"select": [{"id": str(INVITATION_ID)}]},
        "bid_revision_requests": {"select": [
            revision_row(status="declined"),
            revision_row(status="pending"),
        ]},
    }
    c = client_factory(spec)
    r = c.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {row["status"] for row in body} == {"declined", "pending"}


def test_200_empty_when_no_invitations(client_factory):
    spec = {"bid_invitations": {"select": []}}
    c = client_factory(spec)
    r = c.get(URL)
    assert r.status_code == 200
    assert r.json() == []


def test_200_empty_when_no_requests(client_factory):
    spec = {
        "bid_invitations": {"select": [{"id": str(INVITATION_ID)}]},
        "bid_revision_requests": {"select": []},
    }
    c = client_factory(spec)
    r = c.get(URL)
    assert r.status_code == 200
    assert r.json() == []


def test_422_missing_query_param(client_factory):
    c = client_factory({})
    assert c.get("/api/v1/bid-revision-requests").status_code == 422


def test_401_or_403_without_auth(client_factory):
    spec = {"bid_invitations": {"select": []}}
    c = client_factory(spec, auth=False)
    assert c.get(URL).status_code in (401, 403)
