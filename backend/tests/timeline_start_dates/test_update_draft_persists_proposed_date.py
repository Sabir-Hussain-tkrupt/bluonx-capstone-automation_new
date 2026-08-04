"""Task 8.1.5 — PUT /vendor-portal/submissions/{id} persists proposed_start_date."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.routers.vendor_portal as vp
from app.core.supabase_client import get_supabase
from app.core.vendor_auth import get_vendor_context
from app.main import app
from app.models.vendor_portal import BidDraftModel
from app.services.email_service import get_email_service

from .conftest import (
    PROPOSED_START_ISO,
    SUBMISSION_ID,
    _future_dt,
    owned_submission_row,
    revision_request_row,
    vendor_ctx,
)

URL = f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}"


class RecordingDB:
    """Capture update payloads keyed by table."""

    def __init__(self, resolvers: dict):
        self.resolvers = resolvers
        self.updates: dict[str, list] = {}
        self._counts: dict[tuple, int] = {}

    def table(self, name: str):
        outer = self

        class Chain:
            def __init__(self):
                self.op = "select"
                self.cols = ""
                self.payload = None

            def select(self, *a, **k):
                self.op = "select"
                self.cols = a[0] if a else ""
                return self

            def insert(self, payload, *a, **k):
                self.op = "insert"
                self.payload = payload
                return self

            def update(self, payload, *a, **k):
                self.op = "update"
                self.payload = payload
                outer.updates.setdefault(name, []).append(payload)
                return self

            def delete(self, *a, **k):
                self.op = "delete"
                return self

            def __getattr__(self, _name):
                return lambda *a, **k: self

            def execute(self, *a, **k):
                key = (name, self.op, self.cols)
                idx = outer._counts.get(key, 0)
                outer._counts[key] = idx + 1
                resolver = outer.resolvers.get(name)
                data = resolver(self.op, self.cols, self.payload, idx) if resolver else []
                if isinstance(data, Exception):
                    raise data
                res = MagicMock()
                res.data = data
                return res

        return Chain()


@pytest.fixture()
def make_client():
    def _make(resolvers: dict, *, ctx):
        db = RecordingDB(resolvers)
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[get_vendor_context] = lambda: ctx
        app.dependency_overrides[get_email_service] = lambda: MagicMock()
        return TestClient(app), db

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _patch_helpers(monkeypatch):
    async def _tmpl(_db, _inv):
        return "tmpl-id"

    monkeypatch.setattr(vp, "_fetch_template_id_for_invitation", _tmpl)
    monkeypatch.setattr(vp, "fetch_template_items_map", lambda *a, **k: {})
    monkeypatch.setattr(
        vp, "fetch_template_metadata", lambda *a, **k: {"is_lump_sum": True}
    )
    monkeypatch.setattr(vp, "build_line_item_rows", lambda *a, **k: [])
    monkeypatch.setattr(
        vp,
        "load_draft_response",
        lambda _db, sid: BidDraftModel(
            id=str(sid),
            vendor_notes="",
            total_amount=None,
            line_items=[],
            attachment_ids=[],
            last_saved_at=datetime.now(timezone.utc),
            proposed_start_date=None,
        ),
    )
    monkeypatch.setattr(
        vp, "assert_package_open_and_before_deadline", lambda *a, **k: None
    )


def _initial_resolvers():
    def _subs(op, cols, payload, idx):
        if op == "select":
            return [owned_submission_row()]
        return []
    return {"bid_submissions": _subs}


def _revision_resolvers():
    def _subs(op, cols, payload, idx):
        if op == "select":
            return [owned_submission_row()]
        return []

    def _rr(op, cols, payload, idx):
        if "revision_deadline" in cols:
            return [{"id": "rr", "status": "pending", "revision_deadline": _future_dt()}]
        return [revision_request_row()]

    return {"bid_submissions": _subs, "bid_revision_requests": _rr}


# ── Initial branch ────────────────────────────────────────────────────────


def test_initial_update_persists_proposed_start_date(make_client):
    c, db = make_client(_initial_resolvers(), ctx=vendor_ctx(revision=False))
    r = c.put(
        URL,
        json={
            "vendor_notes": "",
            "line_items": [],
            "proposed_start_date": PROPOSED_START_ISO,
        },
    )
    assert r.status_code == 200, r.text
    payload = db.updates["bid_submissions"][0]
    assert payload["proposed_start_date"] == PROPOSED_START_ISO


def test_initial_update_clears_proposed_start_date(make_client):
    c, db = make_client(_initial_resolvers(), ctx=vendor_ctx(revision=False))
    r = c.put(
        URL,
        json={
            "vendor_notes": "",
            "line_items": [],
            "proposed_start_date": None,
        },
    )
    assert r.status_code == 200, r.text
    payload = db.updates["bid_submissions"][0]
    assert payload["proposed_start_date"] is None


# ── Revision branch ───────────────────────────────────────────────────────


def test_revision_update_persists_proposed_start_date(make_client):
    c, db = make_client(_revision_resolvers(), ctx=vendor_ctx(revision=True))
    r = c.put(
        URL,
        json={
            "vendor_notes": "",
            "line_items": [],
            "proposed_start_date": PROPOSED_START_ISO,
        },
    )
    assert r.status_code == 200, r.text
    payload = db.updates["bid_submissions"][0]
    assert payload["proposed_start_date"] == PROPOSED_START_ISO
