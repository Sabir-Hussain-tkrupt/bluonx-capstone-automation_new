"""The upload route enforces the per-submission attachment cap.

Proves the wiring: at the count cap an upload is rejected 409 *before* any
storage work (no blob written); under the cap the same request sails past the
guard and succeeds.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.routers.vendor_portal as vp
from app.core.supabase_client import get_supabase
from app.core.vendor_auth import VendorContext, get_vendor_context
from app.main import app
from app.services.vendor_portal_service import MAX_ATTACHMENTS_PER_SUBMISSION

SUBMISSION_ID = uuid4()
URL = f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}/attachments"


def _ctx() -> VendorContext:
    return VendorContext(
        vendor_id=uuid4(),
        vendor_contact_id=uuid4(),
        bid_invitation_id=uuid4(),
        bid_package_id=uuid4(),
        task_id=uuid4(),
        bid_revision_request_id=None,
    )


class _FakeChain:
    """bid_attachments: select → `existing_count` usage rows; insert → one row."""

    def __init__(self, existing_count: int):
        self.existing_count = existing_count
        self.op = "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def insert(self, *a, **k):
        self.op = "insert"
        return self

    def execute(self, *a, **k):
        res = MagicMock()
        if self.op == "insert":
            res.data = [
                {
                    "id": str(uuid4()),
                    "file_name": "bid.pdf",
                    "file_size": 12,
                    "file_type": "application/pdf",
                    "uploaded_at": "2026-08-05T00:00:00Z",
                }
            ]
        else:
            res.data = [{"file_size": 1024}] * self.existing_count
        return res

    def __getattr__(self, _name):
        return lambda *a, **k: self


class _FakeDB:
    def __init__(self, existing_count: int):
        self.existing_count = existing_count

    def table(self, _name: str):
        return _FakeChain(self.existing_count)


@pytest.fixture()
def spies(monkeypatch):
    monkeypatch.setattr(
        vp, "_fetch_owned_submission",
        lambda *_a, **_k: {"id": str(SUBMISSION_ID), "is_draft": True},
    )
    monkeypatch.setattr(vp, "_assert_draft", lambda *_a, **_k: None)
    monkeypatch.setattr(vp, "assert_package_open_and_before_deadline", lambda *_a, **_k: None)
    monkeypatch.setattr(vp, "validate_upload", MagicMock())
    monkeypatch.setattr(vp, "resolve_unique_filename", lambda *_a, **_k: "bid.pdf")
    upload_spy = MagicMock()
    monkeypatch.setattr(vp, "upload_file", upload_spy)
    app.dependency_overrides[get_vendor_context] = _ctx
    yield upload_spy
    app.dependency_overrides.clear()


def _post() -> "object":
    return TestClient(app).post(
        URL, files={"file": ("bid.pdf", b"%PDF-1.4 small", "application/pdf")}
    )


def test_upload_at_count_cap_is_rejected_before_storage(spies):
    app.dependency_overrides[get_supabase] = lambda: _FakeDB(MAX_ATTACHMENTS_PER_SUBMISSION)
    resp = _post()
    assert resp.status_code == 409, resp.text
    assert "maximum" in resp.text.lower()
    spies.assert_not_called()  # no storage write on a rejected upload


def test_upload_under_cap_succeeds(spies):
    app.dependency_overrides[get_supabase] = lambda: _FakeDB(1)
    resp = _post()
    assert resp.status_code == 201, resp.text
    spies.assert_called_once()  # the guard let it through to storage
