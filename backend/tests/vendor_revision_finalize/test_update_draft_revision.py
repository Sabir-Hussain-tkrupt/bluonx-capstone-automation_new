"""
Step 3 follow-up — update_draft package-guard revision-blindness.

PUT /vendor-portal/submissions/{id}: the only revision-blind spot is
the package guard. Revision JWT must validate the revision request
(not the package deadline/status); initial JWT stays bit-identical.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.routers.vendor_portal as vp
from app.core.supabase_client import get_supabase
from app.core.vendor_auth import get_vendor_context
from app.main import app
from app.models.vendor_portal import BidDraftModel
from app.services.email_service import get_email_service

from .conftest import INVITATION_ID, SUBMISSION_ID, VENDOR_ID, _future, _past, vendor_ctx
from .test_create_draft_revision import RecordingDB

URL = f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}"


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    async def _tmpl(_db, _inv):
        return "tmpl-id"

    monkeypatch.setattr(vp, "_fetch_template_id_for_invitation", _tmpl)
    monkeypatch.setattr(vp, "fetch_template_items_map", lambda *a, **k: {})
    monkeypatch.setattr(vp, "build_line_item_rows", lambda *a, **k: [])
    monkeypatch.setattr(
        vp,
        "load_draft_response",
        lambda _db, sid: BidDraftModel(
            id=str(sid), vendor_notes="", total_amount=None,
            line_items=[], attachment_ids=[],
            last_saved_at=datetime.now(timezone.utc),
        ),
    )


@pytest.fixture()
def make_client():
    def _make(resolvers, *, ctx):
        db = RecordingDB(resolvers)
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[get_vendor_context] = lambda: ctx
        app.dependency_overrides[get_email_service] = lambda: MagicMock()
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def _owned_draft(op, cols, payload, idx):
    if op in ("update", "delete", "insert"):
        return []
    return [{
        "id": str(SUBMISSION_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "vendor_id": str(VENDOR_ID),
        "status": "draft",
        "is_draft": True,
        "total_amount": None,
        "vendor_notes": "",
        "submitted_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }]


def test_revision_update_package_closed_still_200(make_client):
    c = make_client(
        {
            "bid_submissions": _owned_draft,
            "bid_revision_requests": lambda *a: [
                {"id": "rr", "status": "pending", "revision_deadline": _future()}
            ],
            "bid_packages": lambda *a: {"status": "closed", "deadline": _past()},
        },
        ctx=vendor_ctx(revision=True),
    )
    r = c.put(URL, json={"vendor_notes": "x", "line_items": []})
    assert r.status_code == 200, r.text


def test_initial_update_package_closed_still_423(make_client):
    c = make_client(
        {
            "bid_submissions": _owned_draft,
            "bid_packages": lambda *a: {"status": "closed", "deadline": _past()},
        },
        ctx=vendor_ctx(revision=False),
    )
    r = c.put(URL, json={"vendor_notes": "x", "line_items": []})
    assert r.status_code == 423
