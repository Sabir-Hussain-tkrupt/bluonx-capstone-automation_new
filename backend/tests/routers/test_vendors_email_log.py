"""Router tests for GET /api/v1/vendors/{vendor_id}/email-log (Task 7.7).

Verifies the vendor-scoped variant of the broadened email-log filter:
unions email_log rows across bid_invitations, bid_revision_requests, and
bid_submissions reference_types for any invitation this vendor has
received.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app


USER = {
    "user_id": str(uuid4()),
    "email": "admin@example.com",
    "full_name": "Admin",
    "role": "admin",
    "is_active": True,
}


# ── Filter-aware fake DB ───────────────────────────────────────────────────
#
# Mirrors the helper in tests/invitation_tracking/test_bid_package_email_log.py
# but kept local to this module so router tests stay self-contained.


class _Result:
    def __init__(self, data):
        self.data = data


class _Chain:
    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self._filters: list[tuple] = []
        self._single = False
        self._is_null: list[str] = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def is_(self, col, val):
        # Mirror the supabase-py / postgrest is_("col", "null") behavior
        # used by _get_vendor_or_404 — kept rows where the column is None.
        if val == "null":
            self._is_null.append(col)
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        # Mirrors single() here; execute() already returns data=None when the
        # filtered set is empty, which is the maybe_single contract.
        self._single = True
        return self

    def execute(self):
        out = self._rows
        for kind, col, val in self._filters:
            if kind == "eq":
                out = [r for r in out if str(r.get(col)) == str(val)]
            elif kind == "in":
                wanted = {str(v) for v in val}
                out = [r for r in out if str(r.get(col)) in wanted]
        for col in self._is_null:
            out = [r for r in out if r.get(col) is None]
        if self._single:
            return _Result(out[0] if out else None)
        return _Result(out)


class FakeDB:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "vendors": [],
            "bid_invitations": [],
            "bid_revision_requests": [],
            "bid_submissions": [],
            "email_log": [],
        }

    def table(self, name: str) -> _Chain:
        return _Chain(self.tables.get(name, []))


# ── Seed helpers ───────────────────────────────────────────────────────────


def _seed_vendor(db: FakeDB, vendor_id: UUID, *, deleted: bool = False) -> None:
    db.tables["vendors"].append(
        {
            "id": str(vendor_id),
            "company_name": "Acme",
            "deleted_at": "2026-01-01T00:00:00Z" if deleted else None,
        }
    )


def _seed_invitation(db: FakeDB, invitation_id: UUID, vendor_id: UUID) -> None:
    db.tables["bid_invitations"].append(
        {
            "id": str(invitation_id),
            "vendor_id": str(vendor_id),
            "bid_package_id": str(uuid4()),
        }
    )


def _seed_email(
    db: FakeDB,
    *,
    email_id: UUID,
    reference_type: str,
    reference_id: UUID,
    email_type: str = "general",
    subject: str = "subj",
    created_at: datetime | None = None,
) -> None:
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    db.tables["email_log"].append(
        {
            "id": str(email_id),
            "recipient_email": "v@example.com",
            "recipient_type": "vendor_contact",
            "email_type": email_type,
            "subject": subject,
            "reference_type": reference_type,
            "reference_id": str(reference_id),
            "status": "sent",
            "sent_at": created_at.isoformat(),
            "opened_at": None,
            "clicked_at": None,
            "error_message": None,
            "retry_count": 0,
            "created_at": created_at.isoformat(),
        }
    )


# ── Client fixture ─────────────────────────────────────────────────────────


@pytest.fixture()
def db() -> FakeDB:
    return FakeDB()


@pytest.fixture()
def client(db: FakeDB):
    app.dependency_overrides[get_current_active_user] = lambda: USER
    app.dependency_overrides[get_supabase] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _get(client: TestClient, vendor_id: UUID):
    return client.get(f"/api/v1/vendors/{vendor_id}/email-log")


# ── Tests ──────────────────────────────────────────────────────────────────


class TestVendorEmailLog:
    def test_empty_when_vendor_has_no_invitations(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id)

        resp = _get(client, vendor_id)

        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    def test_404_when_vendor_missing(self, client):
        resp = _get(client, uuid4())

        assert resp.status_code == 404

    def test_404_when_vendor_soft_deleted(self, client, db):
        vendor_id = uuid4()
        _seed_vendor(db, vendor_id, deleted=True)

        resp = _get(client, vendor_id)

        assert resp.status_code == 404

    def test_includes_invitation_emails(self, client, db):
        vendor_id, inv_id, email_id = uuid4(), uuid4(), uuid4()
        _seed_vendor(db, vendor_id)
        _seed_invitation(db, inv_id, vendor_id)
        _seed_email(
            db,
            email_id=email_id,
            reference_type="bid_invitations",
            reference_id=inv_id,
            email_type="bid_invitation",
        )

        resp = _get(client, vendor_id)

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["id"] for i in items] == [str(email_id)]
        assert items[0]["email_type"] == "bid_invitation"

    def test_includes_reminder_emails(self, client, db):
        vendor_id, inv_id, invite_email, reminder_email = (uuid4() for _ in range(4))
        _seed_vendor(db, vendor_id)
        _seed_invitation(db, inv_id, vendor_id)
        _seed_email(
            db,
            email_id=invite_email,
            reference_type="bid_invitations",
            reference_id=inv_id,
            email_type="bid_invitation",
        )
        _seed_email(
            db,
            email_id=reminder_email,
            reference_type="bid_invitations",
            reference_id=inv_id,
            email_type="bid_reminder",
        )

        resp = _get(client, vendor_id)

        assert resp.status_code == 200
        ids = {i["id"] for i in resp.json()["items"]}
        assert ids == {str(invite_email), str(reminder_email)}

    def test_includes_revision_request_emails(self, client, db):
        vendor_id, inv_id, rr_id, email_id = (uuid4() for _ in range(4))
        _seed_vendor(db, vendor_id)
        _seed_invitation(db, inv_id, vendor_id)
        db.tables["bid_revision_requests"].append(
            {"id": str(rr_id), "bid_invitation_id": str(inv_id)}
        )
        _seed_email(
            db,
            email_id=email_id,
            reference_type="bid_revision_requests",
            reference_id=rr_id,
        )

        resp = _get(client, vendor_id)

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(email_id)

    def test_includes_initial_bid_receipt_emails(self, client, db):
        vendor_id, inv_id, sub_id, email_id = (uuid4() for _ in range(4))
        _seed_vendor(db, vendor_id)
        _seed_invitation(db, inv_id, vendor_id)
        db.tables["bid_submissions"].append(
            {"id": str(sub_id), "bid_invitation_id": str(inv_id)}
        )
        _seed_email(
            db,
            email_id=email_id,
            reference_type="bid_submissions",
            reference_id=sub_id,
        )

        resp = _get(client, vendor_id)

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(email_id)

    def test_includes_revision_receipt_emails(self, client, db):
        vendor_id, inv_id = uuid4(), uuid4()
        sub1_id, sub2_id = uuid4(), uuid4()
        initial_email, revision_email = uuid4(), uuid4()
        _seed_vendor(db, vendor_id)
        _seed_invitation(db, inv_id, vendor_id)
        db.tables["bid_submissions"].extend(
            [
                {"id": str(sub1_id), "bid_invitation_id": str(inv_id)},
                {"id": str(sub2_id), "bid_invitation_id": str(inv_id)},
            ]
        )
        _seed_email(db, email_id=initial_email,
                    reference_type="bid_submissions", reference_id=sub1_id)
        _seed_email(db, email_id=revision_email,
                    reference_type="bid_submissions", reference_id=sub2_id)

        resp = _get(client, vendor_id)

        ids = {i["id"] for i in resp.json()["items"]}
        assert ids == {str(initial_email), str(revision_email)}

    def test_excludes_other_vendors_emails(self, client, db):
        vendor_a, vendor_b = uuid4(), uuid4()
        inv_a, inv_b = uuid4(), uuid4()
        email_a, email_b = uuid4(), uuid4()
        _seed_vendor(db, vendor_a)
        _seed_vendor(db, vendor_b)
        _seed_invitation(db, inv_a, vendor_a)
        _seed_invitation(db, inv_b, vendor_b)
        _seed_email(db, email_id=email_a, reference_type="bid_invitations",
                    reference_id=inv_a)
        _seed_email(db, email_id=email_b, reference_type="bid_invitations",
                    reference_id=inv_b)

        resp = _get(client, vendor_a)

        ids = {i["id"] for i in resp.json()["items"]}
        assert ids == {str(email_a)}

    def test_sorted_by_created_at_desc(self, client, db):
        vendor_id, inv_id, rr_id, sub_id = (uuid4() for _ in range(4))
        _seed_vendor(db, vendor_id)
        _seed_invitation(db, inv_id, vendor_id)
        db.tables["bid_revision_requests"].append(
            {"id": str(rr_id), "bid_invitation_id": str(inv_id)}
        )
        db.tables["bid_submissions"].append(
            {"id": str(sub_id), "bid_invitation_id": str(inv_id)}
        )
        base = datetime.now(timezone.utc)
        oldest, middle, newest = uuid4(), uuid4(), uuid4()
        _seed_email(db, email_id=oldest, reference_type="bid_invitations",
                    reference_id=inv_id, created_at=base - timedelta(hours=3))
        _seed_email(db, email_id=newest, reference_type="bid_submissions",
                    reference_id=sub_id, created_at=base)
        _seed_email(db, email_id=middle, reference_type="bid_revision_requests",
                    reference_id=rr_id, created_at=base - timedelta(hours=1))

        resp = _get(client, vendor_id)

        ids = [i["id"] for i in resp.json()["items"]]
        assert ids == [str(newest), str(middle), str(oldest)]

    def test_unauthenticated_returns_401(self, db):
        """No auth override → FastAPI's get_current_active_user raises 401."""
        app.dependency_overrides[get_supabase] = lambda: db
        try:
            client = TestClient(app)
            resp = client.get(f"/api/v1/vendors/{uuid4()}/email-log")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()
