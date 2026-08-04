"""
Step 3 follow-up — create_draft revision-blindness.

POST /vendor-portal/submissions must, under a revision JWT:
  - branch the package guard (revision request, not package deadline),
  - NOT 409 on the finalized predecessor,
  - resume an existing revision draft idempotently, else insert a new
    draft carrying supersedes_submission_id + revision_number+1.
Initial-bid behavior stays bit-identical.

A bespoke recording DB is used (not the op-aware make_db): the
revision path issues several *different* bid_submissions SELECTs, so
responses are resolved per (table, op, columns, call-index).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

import app.routers.vendor_portal as vp
from app.core.supabase_client import get_supabase
from app.core.vendor_auth import get_vendor_context
from app.main import app
from app.models.vendor_portal import BidDraftModel
from app.services.email_service import get_email_service

from .conftest import (
    INVITATION_ID,
    SUBMISSION_ID,
    _future,
    _past,
    vendor_ctx,
)

URL = "/api/v1/vendor-portal/submissions"
ORIGINAL_ID = str(SUBMISSION_ID)
NEW_SUB_ID = str(uuid4())
EXISTING_DRAFT_ID = str(uuid4())


def _draft_model(sid: str = NEW_SUB_ID) -> BidDraftModel:
    return BidDraftModel(
        id=sid,
        vendor_notes="",
        total_amount=None,
        line_items=[],
        attachment_ids=[],
        last_saved_at=datetime.now(timezone.utc),
    )


class RecordingDB:
    """db.table(name).<op>(...)....execute(); resolvers see call context."""

    def __init__(self, resolvers: dict):
        self.resolvers = resolvers
        self.inserts: dict[str, list] = {}
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
                outer.inserts.setdefault(name, []).append(payload)
                return self

            def update(self, payload, *a, **k):
                self.op = "update"
                self.payload = payload
                return self

            def delete(self, *a, **k):
                self.op = "delete"
                return self

            def __getattr__(self, _name):
                # eq/neq/in_/order/limit/single/maybe_single → chainable
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
    created = []

    def _make(resolvers: dict, *, ctx):
        db = RecordingDB(resolvers)
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[get_vendor_context] = lambda: ctx
        app.dependency_overrides[get_email_service] = lambda: MagicMock()
        c = TestClient(app)
        created.append((c, db))
        return c, db

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
        vp, "load_draft_response", lambda _db, sid: _draft_model(str(sid))
    )


# ── helpers to build per-table resolvers ───────────────────────────────────


def _rr_resolver(*, original=ORIGINAL_ID, status="pending", missing=False):
    def _r(op, cols, payload, idx):
        if missing:
            return []
        # assert_revision_request_active select: "id, status, revision_deadline"
        if "revision_deadline" in cols:
            return [{"id": "rr", "status": status, "revision_deadline": _future()}]
        # _resolve_revision_draft_target select: "id, original_submission_id, status"
        return [{"id": "rr", "original_submission_id": original, "status": status}]

    return _r


def _subs_resolver(*, predecessor_rev=1, existing_draft_id=None,
                   find_existing_seq=None, new_id=NEW_SUB_ID):
    def _r(op, cols, payload, idx):
        if op == "insert":
            return [{"id": new_id}]
        # predecessor revision_number lookup
        if "revision_number" in cols:
            return [{"revision_number": predecessor_rev}]
        # existing revision-draft probe (select "id" with supersedes filter)
        if cols.strip() == "id":
            return [{"id": existing_draft_id}] if existing_draft_id else []
        # _find_existing_submission select "id, is_draft" (initial path) —
        # supports a per-call sequence for the UNIQUE-recovery test
        if "is_draft" in cols:
            if find_existing_seq is not None:
                return find_existing_seq[min(idx, len(find_existing_seq) - 1)]
            return []
        return []

    return _r


# ── Revision JWT ───────────────────────────────────────────────────────────


def test_revision_no_existing_draft_creates_with_chain(make_client):
    c, db = make_client(
        {
            "bid_revision_requests": _rr_resolver(),
            "bid_submissions": _subs_resolver(predecessor_rev=2),
        },
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL, json={"vendor_notes": "", "line_items": []})
    assert r.status_code == 201, r.text
    payload = db.inserts["bid_submissions"][0]
    assert payload["supersedes_submission_id"] == ORIGINAL_ID
    assert payload["revision_number"] == 3
    assert payload["is_draft"] is True


def test_revision_existing_draft_resumed_no_409(make_client):
    c, db = make_client(
        {
            "bid_revision_requests": _rr_resolver(),
            "bid_submissions": _subs_resolver(existing_draft_id=EXISTING_DRAFT_ID),
        },
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL, json={"vendor_notes": "", "line_items": []})
    assert r.status_code == 201, r.text
    assert r.json()["id"] == EXISTING_DRAFT_ID
    assert "bid_submissions" not in db.inserts  # idempotent — no insert


def test_revision_request_missing_404(make_client):
    c, _ = make_client(
        {
            "bid_revision_requests": _rr_resolver(missing=True),
            "bid_submissions": _subs_resolver(),
        },
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL, json={"vendor_notes": "", "line_items": []})
    assert r.status_code == 404


def test_revision_package_closed_does_not_423(make_client):
    # Guards NOT monkeypatched here: real assert_revision_request_active runs;
    # if the code wrongly called assert_package_open it would query
    # bid_packages — which we make 'closed' → would 423. 201 proves the
    # branch took the revision path and never touched bid_packages.
    c, _ = make_client(
        {
            "bid_revision_requests": _rr_resolver(),
            "bid_submissions": _subs_resolver(predecessor_rev=1),
            "bid_packages": lambda *a: {"status": "closed", "deadline": _past()},
        },
        ctx=vendor_ctx(revision=True),
    )
    r = c.post(URL, json={"vendor_notes": "", "line_items": []})
    assert r.status_code == 201, r.text


# ── Initial-bid regression (bit-identical) ─────────────────────────────────


def test_initial_finalized_exists_still_409_preflight(make_client, monkeypatch):
    monkeypatch.setattr(vp, "assert_package_open_and_before_deadline", lambda *a, **k: None)
    c, _ = make_client(
        {
            "bid_submissions": _subs_resolver(
                find_existing_seq=[[{"id": ORIGINAL_ID, "is_draft": False}]]
            ),
        },
        ctx=vendor_ctx(revision=False),
    )
    r = c.post(URL, json={"vendor_notes": "", "line_items": []})
    assert r.status_code == 409
    assert r.json()["detail"]["detail"] == "Bid already submitted"


def test_initial_unique_violation_recovery_still_409(make_client, monkeypatch):
    monkeypatch.setattr(vp, "assert_package_open_and_before_deadline", lambda *a, **k: None)
    err = APIError({"code": "23505", "message": "duplicate key value"})

    def _subs(op, cols, payload, idx):
        if op == "insert":
            raise err
        if "is_draft" in cols:
            # 1st call (pre-flight) none; 2nd (recovery) finds predecessor
            return [] if idx == 0 else [{"id": ORIGINAL_ID, "is_draft": False}]
        return []

    c, _ = make_client({"bid_submissions": _subs}, ctx=vendor_ctx(revision=False))
    r = c.post(URL, json={"vendor_notes": "", "line_items": []})
    assert r.status_code == 409
    assert r.json()["detail"]["detail"] == "Bid already submitted"


def test_initial_clean_first_time_create_201(make_client, monkeypatch):
    monkeypatch.setattr(vp, "assert_package_open_and_before_deadline", lambda *a, **k: None)
    c, db = make_client(
        {"bid_submissions": _subs_resolver()},  # find_existing → [], insert → new
        ctx=vendor_ctx(revision=False),
    )
    r = c.post(URL, json={"vendor_notes": "", "line_items": []})
    assert r.status_code == 201, r.text
    assert "bid_submissions" in db.inserts
    assert "supersedes_submission_id" not in db.inserts["bid_submissions"][0]
