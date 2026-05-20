"""
Step 3 C.1 — submit_bid revision branch + shared is_draft UPDATE guard.

The heavy post-validation helpers (email context, attachment count,
template lookups, validator, confirmation email) are monkeypatched so
each test exercises only the branch logic + the guarded UPDATE. The
op-aware DB mock feeds the remaining queries.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.routers.vendor_portal as vp

from .conftest import (
    SUBMISSION_ID,
    _future,
    _past,
    committed_submission_row,
    owned_submission_row,
    revision_request_row,
    vendor_ctx,
)

URL = f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}/submit"


@pytest.fixture(autouse=True)
def _patch_finalize_helpers(monkeypatch):
    """Isolate the branch + UPDATE from validation / email / template I/O."""

    async def _tmpl_id(_db, _inv):
        return "tmpl-id"

    async def _send(*_a, **_k):
        return True

    monkeypatch.setattr(vp, "validate_for_submit", lambda **_k: [])
    monkeypatch.setattr(vp, "_fetch_template_id_for_invitation", _tmpl_id)
    monkeypatch.setattr(vp, "fetch_template_metadata", lambda *_a: {"is_lump_sum": False})
    monkeypatch.setattr(vp, "fetch_template_items_map", lambda *_a: {})
    monkeypatch.setattr(vp, "_count_attachments", lambda *_a: 0)
    monkeypatch.setattr(
        vp,
        "_fetch_submission_email_context",
        lambda *_a: {
            "vendor_contact_name": "Jane Roe",
            "vendor_email": "jane@apex.example.com",
            "vendor_company_name": "Apex Grading",
            "project_name": "North Yard",
            "task_name": "Mass Grading",
            "pm_name": None,
            "pm_email": None,
        },
    )
    monkeypatch.setattr(vp, "send_submission_confirmation_email", _send)
    monkeypatch.setattr(vp, "send_revision_submitted_email", _send)


def _revision_spec(*, rr=None, update=None) -> dict:
    return {
        "bid_submissions": {
            "select": [owned_submission_row()],
            "update": update if update is not None else [committed_submission_row()],
        },
        "bid_revision_requests": {"select": rr if rr is not None else [revision_request_row()]},
        "bid_line_items": {"select": []},
    }


def _initial_spec(*, pkg=None, update=None) -> dict:
    return {
        "bid_submissions": {
            "select": [owned_submission_row()],
            "update": update if update is not None else [committed_submission_row()],
        },
        "bid_packages": {
            "select": pkg if pkg is not None
            else {"status": "open", "deadline": _future()}
        },
        "bid_line_items": {"select": []},
    }


# ── Revision branch ────────────────────────────────────────────────────────


def test_submit_revision_happy_path(client_factory):
    c = client_factory(_revision_spec(), ctx=vendor_ctx(revision=True))
    r = c.post(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(SUBMISSION_ID)
    assert body["total_amount"] == "50000.00"


def test_submit_revision_request_not_pending_410(client_factory):
    c = client_factory(
        _revision_spec(rr=[revision_request_row(status="cancelled")]),
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL)
    assert r.status_code == 410
    assert r.json()["detail"] == "This revision request is no longer active"


def test_submit_revision_deadline_passed_410(client_factory):
    c = client_factory(
        _revision_spec(rr=[revision_request_row(revision_deadline=_past())]),
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL)
    assert r.status_code == 410
    assert r.json()["detail"] == "This revision request is no longer active"


def test_submit_revision_request_missing_404(client_factory):
    c = client_factory(_revision_spec(rr=[]), ctx=vendor_ctx(revision=True))
    r = c.post(URL)
    assert r.status_code == 404
    assert r.json()["detail"] == "Revision request not found"


def test_submit_revision_zero_rows_is_draft_returns_409(client_factory):
    c = client_factory(_revision_spec(update=[]), ctx=vendor_ctx(revision=True))
    r = c.post(URL)
    assert r.status_code == 409
    assert r.json()["detail"] == "Bid has already been submitted"


# ── F.2 email branch: revision receipt REPLACES the confirmation ───────────


def test_revision_mode_sends_revision_receipt_only(client_factory, monkeypatch):
    revision_mock = AsyncMock(return_value=True)
    confirm_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(vp, "send_revision_submitted_email", revision_mock)
    monkeypatch.setattr(vp, "send_submission_confirmation_email", confirm_mock)

    c = client_factory(_revision_spec(), ctx=vendor_ctx(revision=True))
    r = c.post(URL)

    assert r.status_code == 200, r.text
    revision_mock.assert_awaited_once()
    confirm_mock.assert_not_awaited()


def test_initial_mode_sends_confirmation_only(client_factory, monkeypatch):
    revision_mock = AsyncMock(return_value=True)
    confirm_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(vp, "send_revision_submitted_email", revision_mock)
    monkeypatch.setattr(vp, "send_submission_confirmation_email", confirm_mock)

    c = client_factory(_initial_spec(), ctx=vendor_ctx(revision=False))
    r = c.post(URL)

    assert r.status_code == 200, r.text
    confirm_mock.assert_awaited_once()
    revision_mock.assert_not_awaited()


# ── Initial-bid regression (must stay bit-identical) ───────────────────────


def test_submit_initial_bid_still_works_regression(client_factory):
    c = client_factory(_initial_spec(), ctx=vendor_ctx(revision=False))
    r = c.post(URL)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(SUBMISSION_ID)


def test_submit_initial_bid_package_closed_still_423(client_factory):
    c = client_factory(
        _initial_spec(pkg={"status": "closed", "deadline": _future()}),
        ctx=vendor_ctx(revision=False),
    )
    r = c.post(URL)
    assert r.status_code == 423


def test_submit_initial_bid_zero_rows_returns_409(client_factory):
    # Documents the spec-mandated 500 -> 409 deviation on the TOCTOU race.
    c = client_factory(_initial_spec(update=[]), ctx=vendor_ctx(revision=False))
    r = c.post(URL)
    assert r.status_code == 409
    assert r.json()["detail"] == "Bid has already been submitted"
