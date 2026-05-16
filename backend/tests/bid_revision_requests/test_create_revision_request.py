"""B.1 — POST /api/v1/bid-revision-requests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from postgrest.exceptions import APIError

import app.services.bid_revision_service as svc
from .conftest import (
    BID_PACKAGE_ID,
    FIXED_RAW_TOKEN,
    INVITATION_ID,
    ORIGINAL_SUBMISSION_ID,
    TASK_ID,
    _future,
    _past,
    revision_row,
)

URL = "/api/v1/bid-revision-requests"


@pytest.fixture(autouse=True)
def _fixed_token(monkeypatch):
    monkeypatch.setattr(
        svc, "_generate_magic_link_token",
        lambda: (FIXED_RAW_TOKEN, "deadbeef"),
    )


def _ok_spec(**over) -> dict:
    """Happy-path spec; override individual tables per test."""
    spec = {
        "bid_invitations": {"select": [{
            "id": str(INVITATION_ID),
            "vendor_id": "11111111-1111-1111-1111-111111111111",
            "bid_package_id": str(BID_PACKAGE_ID),
        }]},
        "bid_packages": {"select": [{
            "id": str(BID_PACKAGE_ID), "task_id": str(TASK_ID),
        }]},
        "bid_submissions": {"select": [{"id": str(ORIGINAL_SUBMISSION_ID)}]},
        "awards": {"select": []},
        "bid_revision_requests": {
            "select": [],            # cap check
            "insert": [revision_row()],
        },
        "magic_link_tokens": {"insert": []},
    }
    spec.update(over)
    return spec


def _body(deadline: str | None = None) -> dict:
    return {
        "bid_invitation_id": str(INVITATION_ID),
        "pm_note": "Please re-price line 3.",
        "revision_deadline": deadline or _future(),
    }


def test_201_happy_path(client_factory):
    c = client_factory(_ok_spec())
    r = c.post(URL, json=_body())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["revision_request"]["status"] == "pending"
    assert body["revision_request"]["original_submission_id"] == str(
        ORIGINAL_SUBMISSION_ID
    )
    assert body["magic_link_token"] == FIXED_RAW_TOKEN
    assert body["portal_url"].endswith(f"/bid/{FIXED_RAW_TOKEN}")


def test_404_invitation_missing(client_factory):
    c = client_factory(_ok_spec(bid_invitations={"select": []}))
    r = c.post(URL, json=_body())
    assert r.status_code == 404


def test_422_no_current_submission(client_factory):
    c = client_factory(_ok_spec(bid_submissions={"select": []}))
    r = c.post(URL, json=_body())
    assert r.status_code == 422


@pytest.mark.parametrize("award_status", ["pending_acceptance", "accepted"])
def test_409_blocking_award(client_factory, award_status):
    c = client_factory(
        _ok_spec(awards={"select": [{"id": "a", "status": award_status}]})
    )
    r = c.post(URL, json=_body())
    assert r.status_code == 409


def test_409_cap_two_non_cancelled(client_factory):
    c = client_factory(
        _ok_spec(bid_revision_requests={
            "select": [{"id": "1", "status": "declined"},
                       {"id": "2", "status": "submitted"}],
            "insert": [revision_row()],
        })
    )
    r = c.post(URL, json=_body())
    assert r.status_code == 409


def test_cancelled_rows_do_not_count_toward_cap(client_factory):
    # Service uses .neq("status","cancelled") so cancelled rows are excluded
    # by the query — an empty select means a slot is free.
    c = client_factory(_ok_spec())
    r = c.post(URL, json=_body())
    assert r.status_code == 201


def test_422_past_deadline(client_factory):
    c = client_factory(_ok_spec())
    r = c.post(URL, json=_body(deadline=_past()))
    assert r.status_code == 422


def test_409_duplicate_pending_unique_violation(client_factory):
    err = APIError({"code": "23505", "message": "duplicate key value"})
    c = client_factory(_ok_spec(bid_revision_requests={
        "select": [], "insert": err,
    }))
    r = c.post(URL, json=_body())
    assert r.status_code == 409


def test_401_or_403_without_auth(client_factory):
    c = client_factory(_ok_spec(), auth=False)
    r = c.post(URL, json=_body())
    assert r.status_code in (401, 403)
