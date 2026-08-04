"""Point 6 hardening — draft routes persist the server-derived total.

For a structured template the client's total_amount is ignored: create and
update both store the Decimal sum of the line items. Lump-sum templates keep
the vendor's own total (their sole pricing input).
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

NEW_SUB_ID = str(uuid4())
EXISTING_SUB_ID = str(uuid4())
TID1 = str(uuid4())  # unit_price line
TID2 = str(uuid4())  # lump_sum line

CREATE_URL = "/api/v1/vendor-portal/submissions"
UPDATE_URL = f"/api/v1/vendor-portal/submissions/{EXISTING_SUB_ID}"


def _template_map() -> dict:
    return {
        TID1: {
            "description": "Excavation",
            "item_type": "unit_price",
            "unit_of_measure": "CY",
            "sort_order": 1,
        },
        TID2: {
            "description": "Mobilization",
            "item_type": "lump_sum",
            "unit_of_measure": None,
            "sort_order": 2,
        },
    }


# Structured lines: 0.1 * 0.1 = 0.01, plus a 500 lump sum → 500.01. The client
# sends a deliberately wrong total that the server must discard.
STRUCTURED_LINES = [
    {"template_item_id": TID1, "quantity": "0.1", "unit_price": "0.1"},
    {"template_item_id": TID2, "lump_sum_amount": "500"},
]
BOGUS_CLIENT_TOTAL = "999999.99"
DERIVED_TOTAL = "500.01"


def _draft_model(sid: str) -> BidDraftModel:
    return BidDraftModel(
        id=sid,
        vendor_notes="",
        total_amount=None,
        line_items=[],
        attachment_ids=[],
        last_saved_at=datetime.now(timezone.utc),
        proposed_start_date=None,
    )


class RecordingDB:
    """Captures insert + update payloads per table; chain methods are no-ops."""

    def __init__(self):
        self.inserts: dict[str, list] = {}
        self.updates: dict[str, list] = {}

    def table(self, name: str):
        outer = self

        class Chain:
            def __init__(self):
                self.op = "select"

            def select(self, *a, **k):
                self.op = "select"
                return self

            def insert(self, payload, *a, **k):
                self.op = "insert"
                outer.inserts.setdefault(name, []).append(payload)
                return self

            def update(self, payload, *a, **k):
                self.op = "update"
                outer.updates.setdefault(name, []).append(payload)
                return self

            def delete(self, *a, **k):
                self.op = "delete"
                return self

            def __getattr__(self, _name):
                return lambda *a, **k: self

            def execute(self, *a, **k):
                res = MagicMock()
                res.data = [{"id": NEW_SUB_ID}] if self.op == "insert" else []
                return res

        return Chain()


def _ctx() -> VendorContext:
    return VendorContext(
        vendor_id=uuid4(),
        vendor_contact_id=uuid4(),
        bid_invitation_id=uuid4(),
        bid_package_id=uuid4(),
        task_id=uuid4(),
        bid_revision_request_id=None,
    )


@pytest.fixture()
def client_db():
    db = RecordingDB()
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_vendor_context] = _ctx
    app.dependency_overrides[get_email_service] = lambda: MagicMock()
    yield TestClient(app), db
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _patch_helpers(monkeypatch):
    async def _tmpl(_db, _inv):
        return "tmpl-id"

    monkeypatch.setattr(vp, "_fetch_template_id_for_invitation", _tmpl)
    monkeypatch.setattr(vp, "fetch_template_items_map", lambda *a, **k: _template_map())
    monkeypatch.setattr(
        vp, "fetch_template_metadata", lambda *a, **k: {"is_lump_sum": False}
    )
    monkeypatch.setattr(vp, "assert_package_open_and_before_deadline", lambda *a, **k: None)
    monkeypatch.setattr(vp, "load_draft_response", lambda _db, sid: _draft_model(str(sid)))
    # create path: no existing submission for this invitation.
    monkeypatch.setattr(vp, "_find_existing_submission", lambda *a, **k: None)
    # update path: an owned draft row, and skip the draft assertion.
    monkeypatch.setattr(
        vp,
        "_fetch_owned_submission",
        lambda *a, **k: {"id": EXISTING_SUB_ID, "is_draft": True, "status": "draft"},
    )
    monkeypatch.setattr(vp, "_assert_draft", lambda *a, **k: None)
    # build_line_item_rows / compute_total_amount run for real (the code under test).


def test_create_stores_server_derived_total_for_structured(client_db):
    c, db = client_db
    r = c.post(
        CREATE_URL,
        json={
            "vendor_notes": "",
            "total_amount": BOGUS_CLIENT_TOTAL,
            "line_items": STRUCTURED_LINES,
            "proposed_start_date": None,
        },
    )
    assert r.status_code == 201, r.text
    stored = db.inserts["bid_submissions"][0]["total_amount"]
    assert stored == DERIVED_TOTAL
    assert stored != BOGUS_CLIENT_TOTAL


def test_update_stores_server_derived_total_for_structured(client_db):
    c, db = client_db
    r = c.put(
        UPDATE_URL,
        json={
            "vendor_notes": "",
            "total_amount": BOGUS_CLIENT_TOTAL,
            "line_items": STRUCTURED_LINES,
            "proposed_start_date": None,
        },
    )
    assert r.status_code == 200, r.text
    stored = db.updates["bid_submissions"][0]["total_amount"]
    assert stored == DERIVED_TOTAL
    assert stored != BOGUS_CLIENT_TOTAL
