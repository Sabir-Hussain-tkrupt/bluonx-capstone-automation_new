"""Task 8.1.5 — end-to-end submit guard for proposed_start_date.

Exercises the REAL validate_for_submit through the FastAPI route. Other
heavy helpers (email, attachment count, template fetches) stay mocked.

Matrix per branch:
  - package has desired_start_date, submission proposed=None → 422
  - package has desired_start_date, submission proposed=set  → 200
  - package has NO desired_start_date, submission proposed=None → 200
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.routers.vendor_portal as vp

from .conftest import (
    DESIRED_START_ISO,
    PROPOSED_START_ISO,
    SUBMISSION_ID,
    _future_dt,
    committed_submission_row,
    owned_submission_row,
    package_row,
    revision_request_row,
    vendor_ctx,
)

URL = f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}/submit"


@pytest.fixture(autouse=True)
def _patch_finalize_helpers(monkeypatch):
    """Isolate the route + REAL validator from email/template I/O."""

    async def _tmpl_id(_db, _inv):
        return "tmpl-id"

    async def _send(*_a, **_k):
        return True

    # Real validator runs (NOT monkeypatched)
    monkeypatch.setattr(vp, "_fetch_template_id_for_invitation", _tmpl_id)
    # Use lump_sum template so per-line checks are skipped, isolating
    # the new proposed_start_date rule.
    monkeypatch.setattr(
        vp, "fetch_template_metadata", lambda *_a: {"is_lump_sum": True}
    )
    monkeypatch.setattr(vp, "fetch_template_items_map", lambda *_a: {})
    monkeypatch.setattr(vp, "_count_attachments", lambda *_a: 0)
    monkeypatch.setattr(
        vp,
        "_fetch_submission_email_context",
        lambda *_a: {
            "vendor_contact_name": "Jane Roe",
            "vendor_email": "jane@a.example",
            "vendor_company_name": "Apex",
            "project_name": "North Yard",
            "task_name": "Mass Grading",
            "pm_name": None,
            "pm_email": None,
        },
    )
    monkeypatch.setattr(vp, "send_submission_confirmation_email", _send)
    monkeypatch.setattr(vp, "send_revision_submitted_email", _send)


def _initial_spec(*, desired=DESIRED_START_ISO, proposed=None) -> dict:
    return {
        "bid_submissions": {
            "select": [owned_submission_row(proposed_start_date=proposed)],
            "update": [committed_submission_row(proposed_start_date=proposed)],
        },
        "bid_packages": {
            "select": package_row(desired_start_date=desired),
        },
        "bid_line_items": {"select": []},
    }


def _revision_spec(*, desired=DESIRED_START_ISO, proposed=None) -> dict:
    return {
        "bid_submissions": {
            "select": [owned_submission_row(proposed_start_date=proposed)],
            "update": [committed_submission_row(proposed_start_date=proposed)],
        },
        "bid_revision_requests": {"select": [revision_request_row()]},
        "bid_packages": {
            "select": package_row(desired_start_date=desired),
        },
        "bid_line_items": {"select": []},
    }


# ── INITIAL branch ────────────────────────────────────────────────────────


def test_initial_rejects_null_proposed_when_desired_present(client_factory):
    c = client_factory(
        _initial_spec(desired=DESIRED_START_ISO, proposed=None),
        ctx=vendor_ctx(revision=False),
    )
    r = c.post(URL)
    assert r.status_code == 422, r.text
    body = r.json()
    fields = [e["field"] for e in body["detail"]["errors"]]
    assert "proposed_start_date" in fields


def test_initial_accepts_proposed_when_desired_present(client_factory):
    c = client_factory(
        _initial_spec(desired=DESIRED_START_ISO, proposed=PROPOSED_START_ISO),
        ctx=vendor_ctx(revision=False),
    )
    r = c.post(URL)
    assert r.status_code == 200, r.text


def test_initial_accepts_null_proposed_when_desired_absent(client_factory):
    c = client_factory(
        _initial_spec(desired=None, proposed=None),
        ctx=vendor_ctx(revision=False),
    )
    r = c.post(URL)
    assert r.status_code == 200, r.text


# ── REVISION branch ───────────────────────────────────────────────────────


def test_revision_rejects_null_proposed_when_desired_present(client_factory):
    c = client_factory(
        _revision_spec(desired=DESIRED_START_ISO, proposed=None),
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL)
    assert r.status_code == 422, r.text
    fields = [e["field"] for e in r.json()["detail"]["errors"]]
    assert "proposed_start_date" in fields


def test_revision_accepts_proposed_when_desired_present(client_factory):
    c = client_factory(
        _revision_spec(desired=DESIRED_START_ISO, proposed=PROPOSED_START_ISO),
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL)
    assert r.status_code == 200, r.text


def test_revision_accepts_null_proposed_when_desired_absent(client_factory):
    c = client_factory(
        _revision_spec(desired=None, proposed=None),
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL)
    assert r.status_code == 200, r.text
