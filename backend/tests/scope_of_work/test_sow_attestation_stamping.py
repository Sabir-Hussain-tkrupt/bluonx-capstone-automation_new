"""Signed Scope of Work — attestation persistence + stamp timing.

Locks the contract that:
  - create_draft / update_draft persist `sow_attested_name` but NEVER set
    the `sow_attested_at` stamp,
  - submit_bid (finalize) sets `sow_attested_at`.

Uses a recording Supabase mock + monkeypatched finalize helpers so only the
bid_submissions write payloads are under test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.routers.vendor_portal as vp
from app.core.supabase_client import get_supabase
from app.core.vendor_auth import VendorContext, get_vendor_context
from app.main import app
from app.models.vendor_portal import BidDraftModel
from app.services.email_service import get_email_service

VENDOR_ID = uuid4()
VENDOR_CONTACT_ID = uuid4()
INVITATION_ID = uuid4()
BID_PACKAGE_ID = uuid4()
TASK_ID = uuid4()
SUBMISSION_ID = uuid4()


def _ctx() -> VendorContext:
    return VendorContext(
        vendor_id=VENDOR_ID,
        vendor_contact_id=VENDOR_CONTACT_ID,
        bid_invitation_id=INVITATION_ID,
        bid_package_id=BID_PACKAGE_ID,
        task_id=TASK_ID,
        bid_revision_request_id=None,
    )


class RecordingDB:
    """Records write payloads per (table, op); returns configured select data."""

    def __init__(self, selects: dict):
        self.selects = selects
        self.writes: dict[str, list] = {}

    def table(self, name: str):
        outer = self

        class Chain:
            def __init__(self):
                self.op = "select"

            def select(self, *a, **k):
                self.op = "select"
                return self

            def insert(self, payload, *a, **k):
                outer.writes.setdefault(f"{name}.insert", []).append(payload)
                self.op = "insert"
                self._payload = payload
                return self

            def update(self, payload, *a, **k):
                outer.writes.setdefault(f"{name}.update", []).append(payload)
                self.op = "update"
                self._payload = payload
                return self

            def delete(self, *a, **k):
                self.op = "delete"
                return self

            def eq(self, *a, **k):
                return self

            def is_(self, *a, **k):
                return self

            def in_(self, *a, **k):
                return self

            def order(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def single(self, *a, **k):
                return self

            def maybe_single(self, *a, **k):
                return self

            def execute(self, *a, **k):
                res = MagicMock()
                if self.op == "insert":
                    row = dict(self._payload)
                    row.setdefault("id", str(SUBMISSION_ID))
                    res.data = [row]
                elif self.op == "update":
                    res.data = [{"id": str(SUBMISSION_ID), "total_amount": "1000.00"}]
                else:
                    res.data = outer.selects.get(name, [])
                return res

        return Chain()


@pytest.fixture()
def client_and_db(monkeypatch):
    def _make(selects, ctx=None):
        db = RecordingDB(selects)
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[get_vendor_context] = lambda: ctx or _ctx()
        app.dependency_overrides[get_email_service] = lambda: MagicMock()
        return TestClient(app), db

    yield _make
    app.dependency_overrides.clear()


def _draft_model() -> BidDraftModel:
    return BidDraftModel(
        id=str(SUBMISSION_ID),
        vendor_notes="",
        total_amount=None,
        line_items=[],
        attachment_ids=[],
        last_saved_at=datetime.now(timezone.utc),
        sow_attested_name="ACME GRADING",
    )


def _patch_common(monkeypatch):
    async def _tmpl_id(_db, _inv):
        return "tmpl-id"

    monkeypatch.setattr(vp, "_fetch_template_id_for_invitation", _tmpl_id)
    monkeypatch.setattr(vp, "fetch_template_items_map", lambda *_a: {})
    monkeypatch.setattr(vp, "load_draft_response", lambda *_a, **_k: _draft_model())
    monkeypatch.setattr(vp, "assert_package_open_and_before_deadline", lambda *_a, **_k: None)


def test_create_draft_persists_name_but_not_stamp(client_and_db, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(vp, "_find_existing_submission", lambda *_a, **_k: None)

    client, db = client_and_db(selects={})
    resp = client.post(
        "/api/v1/vendor-portal/submissions",
        json={
            "vendor_notes": "",
            "total_amount": "1000.00",
            "line_items": [],
            "attachment_ids": [],
            "sow_attested_name": "ACME GRADING",
        },
    )
    assert resp.status_code == 201, resp.text
    insert = db.writes["bid_submissions.insert"][0]
    assert insert["sow_attested_name"] == "ACME GRADING"
    assert "sow_attested_at" not in insert


def test_update_draft_persists_name_but_not_stamp(client_and_db, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        vp, "_fetch_owned_submission",
        lambda *_a, **_k: {"id": str(SUBMISSION_ID), "is_draft": True},
    )

    client, db = client_and_db(selects={})
    resp = client.put(
        f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}",
        json={
            "vendor_notes": "notes",
            "total_amount": "1000.00",
            "line_items": [],
            "attachment_ids": [],
            "sow_attested_name": "ACME GRADING",
        },
    )
    assert resp.status_code == 200, resp.text
    update = db.writes["bid_submissions.update"][0]
    assert update["sow_attested_name"] == "ACME GRADING"
    assert "sow_attested_at" not in update


def test_submit_sets_attestation_stamp(client_and_db, monkeypatch):
    async def _tmpl_id(_db, _inv):
        return "tmpl-id"

    monkeypatch.setattr(vp, "_fetch_template_id_for_invitation", _tmpl_id)
    monkeypatch.setattr(vp, "fetch_template_metadata", lambda *_a: {"is_lump_sum": True})
    monkeypatch.setattr(vp, "fetch_template_items_map", lambda *_a: {})
    monkeypatch.setattr(vp, "_count_attachments", lambda *_a: 0)
    monkeypatch.setattr(vp, "assert_package_open_and_before_deadline", lambda *_a, **_k: None)
    monkeypatch.setattr(
        vp, "_fetch_owned_submission",
        lambda *_a, **_k: {
            "id": str(SUBMISSION_ID),
            "is_draft": True,
            "total_amount": "1000.00",
            "vendor_notes": "",
            "proposed_start_date": None,
            "sow_attested_name": "ACME GRADING",
        },
    )

    async def _send(*_a, **_k):
        return True

    monkeypatch.setattr(vp, "send_submission_confirmation_email", _send)
    monkeypatch.setattr(vp, "send_revision_submitted_email", _send)
    monkeypatch.setattr(
        vp, "_fetch_submission_email_context",
        lambda *_a, **_k: {
            "vendor_email": "v@a.example",
            "vendor_company_name": "Acme",
            "project_name": "P",
            "task_name": "T",
        },
    )

    # Package row (no desired date) for the timeline check.
    client, db = client_and_db(selects={"bid_packages": [{"desired_start_date": None}]})
    resp = client.post(f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}/submit")
    assert resp.status_code == 200, resp.text
    update = db.writes["bid_submissions.update"][0]
    assert update["is_draft"] is False
    assert "sow_attested_at" in update and update["sow_attested_at"]
