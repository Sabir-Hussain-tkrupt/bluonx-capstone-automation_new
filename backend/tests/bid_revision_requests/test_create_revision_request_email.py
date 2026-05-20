"""F.1 — create_revision_request_endpoint dispatches the vendor email.

The helper is monkeypatched on the router module (where it is imported)
so we can assert it is awaited with the right context, and that a raised
send never turns the committed 201 into an error (best-effort).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.routers.bid_revisions as router_mod
from .conftest import (
    BID_PACKAGE_ID,
    INVITATION_ID,
    ORIGINAL_SUBMISSION_ID,
    TASK_ID,
    _future,
    revision_row,
)

URL = "/api/v1/bid-revision-requests"


def _ok_spec(**over) -> dict:
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
            "select": [],
            "insert": [revision_row()],
        },
        "magic_link_tokens": {"insert": []},
    }
    spec.update(over)
    return spec


def _body() -> dict:
    return {
        "bid_invitation_id": str(INVITATION_ID),
        "pm_note": "Please re-price line 3.",
        "revision_deadline": _future(),
    }


def test_create_dispatches_revision_request_email(client_factory, monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(router_mod, "send_revision_request_email", mock)

    c = client_factory(_ok_spec())
    r = c.post(URL, json=_body())

    assert r.status_code == 201, r.text
    mock.assert_awaited_once()
    kwargs = mock.await_args.kwargs
    assert str(kwargs["bid_invitation_id"]) == str(INVITATION_ID)
    assert kwargs["pm_note"] == "Please re-price line 3."
    assert kwargs["portal_url"].endswith(
        "/bid/%s" % r.json()["magic_link_token"]
    )
    assert kwargs["revision_request_id"] is not None


def test_201_still_returned_when_email_send_raises(client_factory, monkeypatch):
    mock = AsyncMock(side_effect=RuntimeError("smtp exploded"))
    monkeypatch.setattr(router_mod, "send_revision_request_email", mock)

    c = client_factory(_ok_spec())
    r = c.post(URL, json=_body())

    assert r.status_code == 201, r.text
    mock.assert_awaited_once()
