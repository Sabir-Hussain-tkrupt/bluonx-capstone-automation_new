"""Router tests for GET /api/v1/vendors/{vendor_id}/email-log.

The endpoint reads v_vendor_email_log, which resolves email_log's polymorphic
reference to a vendor across five flows (bid_invitations, bid_revision_requests,
bid_submissions, awards, milestones) and keeps only vendor-directed mail. The
union and the attribution are the view's job now, so these tests seed view rows
and pin the endpoint's contract instead: the paginated envelope, correct
slicing, newest-first ordering, and the vendor 404 guard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app
from tests._fakes import FakeRowsSupabase


USER = {
    "user_id": str(uuid4()),
    "email": "admin@example.com",
    "full_name": "Admin",
    "role": "admin",
    "is_active": True,
}

VIEW = "v_vendor_email_log"
BASE = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


# ── Seed helpers ───────────────────────────────────────────────────────────


def _seed_vendor(db: FakeRowsSupabase, vendor_id: UUID, *, deleted: bool = False) -> None:
    db.tables.setdefault("vendors", []).append(
        {
            "id": str(vendor_id),
            "company_name": "Acme",
            "deleted_at": "2026-01-01T00:00:00Z" if deleted else None,
        }
    )


def _seed_email(
    db: FakeRowsSupabase,
    vendor_id: UUID,
    *,
    email_id: UUID | None = None,
    reference_type: str = "bid_invitations",
    email_type: str = "general",
    subject: str = "subj",
    minutes_ago: int = 0,
) -> UUID:
    """Append one v_vendor_email_log row. Larger minutes_ago = older."""
    email_id = email_id or uuid4()
    created = BASE - timedelta(minutes=minutes_ago)
    db.tables.setdefault(VIEW, []).append(
        {
            "id": str(email_id),
            "recipient_email": "v@example.com",
            "recipient_type": "vendor_contact",
            "email_type": email_type,
            "subject": subject,
            "reference_type": reference_type,
            "reference_id": str(uuid4()),
            "status": "sent",
            "sent_at": created.isoformat(),
            "opened_at": None,
            "clicked_at": None,
            "error_message": None,
            "retry_count": 0,
            "created_at": created.isoformat(),
            "vendor_id": str(vendor_id),
            "bid_invitation_id": None,
            "bid_package_id": None,
        }
    )
    return email_id


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def db() -> FakeRowsSupabase:
    return FakeRowsSupabase({"vendors": [], VIEW: []})


@pytest.fixture()
def client(db: FakeRowsSupabase):
    app.dependency_overrides[get_current_active_user] = lambda: USER
    app.dependency_overrides[get_supabase] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _get(client: TestClient, vendor_id: UUID, **params):
    return client.get(f"/api/v1/vendors/{vendor_id}/email-log", params=params)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestVendorEmailLog:
    def test_returns_a_paginated_envelope(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)
        _seed_email(db, vendor_id, subject="hello", email_type="bid_invitation")

        resp = _get(client, vendor_id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 25
        assert [i["subject"] for i in body["items"]] == ["hello"]
        assert body["items"][0]["email_type"] == "bid_invitation"

    def test_empty_when_vendor_has_no_emails(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)

        resp = _get(client, vendor_id)

        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0, "page": 1, "page_size": 25}

    def test_excludes_other_vendors_emails(self, client, db):
        mine, theirs = uuid4(), uuid4()
        _seed_vendor(db, mine)
        _seed_email(db, mine, subject="mine")
        _seed_email(db, theirs, subject="theirs")

        body = _get(client, mine).json()

        assert body["total"] == 1
        assert [i["subject"] for i in body["items"]] == ["mine"]

    def test_orders_newest_first(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)
        _seed_email(db, vendor_id, subject="older", minutes_ago=180)
        _seed_email(db, vendor_id, subject="newest", minutes_ago=0)
        _seed_email(db, vendor_id, subject="middle", minutes_ago=60)

        body = _get(client, vendor_id).json()

        assert [i["subject"] for i in body["items"]] == ["newest", "middle", "older"]

    def test_page_two_returns_the_next_slice(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)
        for i in range(5):
            _seed_email(db, vendor_id, subject=f"e{i}", minutes_ago=i)

        first = _get(client, vendor_id, page=1, page_size=2).json()
        second = _get(client, vendor_id, page=2, page_size=2).json()

        assert first["total"] == second["total"] == 5
        assert [i["subject"] for i in first["items"]] == ["e0", "e1"]
        assert [i["subject"] for i in second["items"]] == ["e2", "e3"]
        assert second["page"] == 2

    def test_page_past_the_end_is_empty_but_reports_the_true_total(self, client, db):
        # Degrade to an empty page rather than erroring, matching list_vendors.
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)
        _seed_email(db, vendor_id)

        body = _get(client, vendor_id, page=9, page_size=25).json()

        assert body["items"] == []
        assert body["total"] == 1

    def test_includes_the_three_invitation_linked_flows(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)
        _seed_email(db, vendor_id, reference_type="bid_invitations", subject="invite")
        _seed_email(db, vendor_id, reference_type="bid_revision_requests", subject="revise")
        _seed_email(db, vendor_id, reference_type="bid_submissions", subject="receipt")

        body = _get(client, vendor_id).json()

        assert body["total"] == 3
        assert {i["subject"] for i in body["items"]} == {"invite", "revise", "receipt"}

    def test_includes_award_and_milestone_emails(self, client, db):
        # Both were silently absent before: the old reader unioned only the
        # three invitation-linked reference_types.
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)
        _seed_email(db, vendor_id, reference_type="awards", subject="awarded")
        _seed_email(db, vendor_id, reference_type="milestones", subject="check-in")

        body = _get(client, vendor_id).json()

        assert body["total"] == 2
        assert {i["subject"] for i in body["items"]} == {"awarded", "check-in"}

    def test_rejects_an_out_of_range_page_or_page_size(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)

        assert _get(client, vendor_id, page_size=500).status_code == 422
        assert _get(client, vendor_id, page=0).status_code == 422

    def test_404_when_vendor_missing(self, client):
        assert _get(client, uuid4()).status_code == 404

    def test_404_when_vendor_soft_deleted(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id, deleted=True)

        assert _get(client, vendor_id).status_code == 404

    def test_unauthenticated_returns_401(self, db):
        """No auth override → FastAPI's get_current_active_user raises 401."""
        app.dependency_overrides[get_supabase] = lambda: db
        try:
            client = TestClient(app)
            resp = client.get(f"/api/v1/vendors/{uuid4()}/email-log")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()
