"""Integrity guards on vendor contacts.

A vendor must always keep at least one contact, and one of those must be
primary. Creation enforces both (`_create_vendor_with_contacts`), but until
these guards existed nothing enforced them afterwards, so the contacts tab
could leave a vendor with no contacts — or no primary — at all. That matters
because the invitation and milestone email paths resolve a recipient through
`is_primary` (see services/vendor_filtering.py, milestone_email_service.py,
milestone_token_service.py); a vendor in that state silently stops being
reachable.

The fake below applies eq/neq filters for real rather than rubber-stamping
whatever the router asks for — otherwise these tests would pass against the
unguarded code.
"""

from __future__ import annotations

from uuid import uuid4

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

VENDOR_ID = str(uuid4())


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, fake: "FakeDB", table: str):
        self._fake = fake
        self._table = table
        self._filters: list[tuple] = []
        self._op = "select"
        self._payload = None
        self._want_count = False
        self._single = False

    def select(self, *_a, count=None, **_k):
        self._op = "select"
        if count == "exact":
            self._want_count = True
        return self

    def insert(self, payload=None, *_a, **_k):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload=None, *_a, **_k):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self, *_a, **_k):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def maybe_single(self, *_a, **_k):
        self._single = True
        return self

    def single(self, *_a, **_k):
        self._single = True
        return self

    def execute(self):
        return self._fake._resolve(self)


def _matches(row, filters) -> bool:
    for kind, col, val in filters:
        actual = row.get(col)
        if kind == "eq":
            # Booleans and ids both compare fine as-is; stringify ids only.
            if isinstance(actual, bool) or isinstance(val, bool):
                if actual != val:
                    return False
            elif str(actual) != str(val):
                return False
        if kind == "neq" and str(actual) == str(val):
            return False
        if kind == "is":
            if val == "null" and actual is not None:
                return False
    return True


class FakeDB:
    def __init__(self, contacts: list[dict], vendor_deleted: bool = False):
        self.contacts = contacts
        self.vendors = [
            {
                "id": VENDOR_ID,
                "company_name": "Acme",
                "deleted_at": "2026-01-01T00:00:00Z" if vendor_deleted else None,
            }
        ]
        self.deleted_ids: list[str] = []
        self.updates: list[tuple[str, dict]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _rows(self, table: str) -> list[dict]:
        return self.vendors if table == "vendors" else self.contacts

    def _resolve(self, q: _Query):
        rows = [r for r in self._rows(q._table) if _matches(r, q._filters)]

        if q._op == "select":
            if q._single:
                return _Result(rows[0] if rows else None)
            return _Result(rows, count=len(rows) if q._want_count else None)

        if q._op == "delete":
            for r in rows:
                self.contacts.remove(r)
                self.deleted_ids.append(r["id"])
            return _Result(rows)

        if q._op == "update":
            for r in rows:
                r.update(q._payload or {})
                self.updates.append((r["id"], q._payload or {}))
            return _Result(rows)

        if q._op == "insert":
            row = {
                "id": str(uuid4()),
                "phone": None,
                "title": None,
                "is_primary": False,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                **(q._payload or {}),
            }
            self.contacts.append(row)
            return _Result([row])

        return _Result([])


def _contact(*, primary: bool, name: str = "Dana Reed") -> dict:
    return {
        "id": str(uuid4()),
        "vendor_id": VENDOR_ID,
        "full_name": name,
        "email": f"{name.split()[0].lower()}@example.com",
        "phone": None,
        "title": None,
        "is_primary": primary,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture()
def client_with():
    def _bind(fake):
        app.dependency_overrides[get_current_active_user] = lambda: USER
        app.dependency_overrides[get_supabase] = lambda: fake
        return TestClient(app)

    yield _bind
    app.dependency_overrides.clear()


class TestLastContactCannotBeDeleted:
    def test_deleting_the_only_contact_is_rejected(self, client_with):
        only = _contact(primary=True)
        fake = FakeDB([only])
        client = client_with(fake)

        resp = client.delete(f"/api/v1/vendors/{VENDOR_ID}/contacts/{only['id']}")

        assert resp.status_code == 409
        assert "only contact" in resp.json()["detail"]
        # And it really is still there.
        assert fake.contacts == [only]

    def test_deleting_one_of_two_still_works(self, client_with):
        primary, secondary = _contact(primary=True), _contact(primary=False, name="Sam Lee")
        fake = FakeDB([primary, secondary])
        client = client_with(fake)

        resp = client.delete(f"/api/v1/vendors/{VENDOR_ID}/contacts/{secondary['id']}")

        assert resp.status_code == 204
        assert fake.deleted_ids == [secondary["id"]]

    def test_deleting_the_primary_promotes_the_survivor(self, client_with):
        primary, secondary = _contact(primary=True), _contact(primary=False, name="Sam Lee")
        fake = FakeDB([primary, secondary])
        client = client_with(fake)

        resp = client.delete(f"/api/v1/vendors/{VENDOR_ID}/contacts/{primary['id']}")

        assert resp.status_code == 204
        assert secondary["is_primary"] is True

    def test_unknown_contact_is_404_not_409(self, client_with):
        fake = FakeDB([_contact(primary=True)])
        client = client_with(fake)

        resp = client.delete(f"/api/v1/vendors/{VENDOR_ID}/contacts/{uuid4()}")

        assert resp.status_code == 404


class TestPrimaryCannotBeLeftUnset:
    def test_clearing_the_only_primary_is_rejected(self, client_with):
        primary, secondary = _contact(primary=True), _contact(primary=False, name="Sam Lee")
        fake = FakeDB([primary, secondary])
        client = client_with(fake)

        resp = client.patch(
            f"/api/v1/vendors/{VENDOR_ID}/contacts/{primary['id']}",
            json={"is_primary": False},
        )

        assert resp.status_code == 409
        assert "primary contact" in resp.json()["detail"]
        assert primary["is_primary"] is True

    def test_clearing_a_non_primary_is_a_harmless_no_op(self, client_with):
        primary, secondary = _contact(primary=True), _contact(primary=False, name="Sam Lee")
        fake = FakeDB([primary, secondary])
        client = client_with(fake)

        resp = client.patch(
            f"/api/v1/vendors/{VENDOR_ID}/contacts/{secondary['id']}",
            json={"is_primary": False},
        )

        assert resp.status_code == 200

    def test_promoting_another_contact_is_the_supported_path(self, client_with):
        primary, secondary = _contact(primary=True), _contact(primary=False, name="Sam Lee")
        fake = FakeDB([primary, secondary])
        client = client_with(fake)

        resp = client.patch(
            f"/api/v1/vendors/{VENDOR_ID}/contacts/{secondary['id']}",
            json={"is_primary": True},
        )

        assert resp.status_code == 200
        assert secondary["is_primary"] is True
        assert primary["is_primary"] is False

    def test_unrelated_patch_is_unaffected_by_the_guard(self, client_with):
        primary = _contact(primary=True)
        fake = FakeDB([primary])
        client = client_with(fake)

        resp = client.patch(
            f"/api/v1/vendors/{VENDOR_ID}/contacts/{primary['id']}",
            json={"phone": "555-0100"},
        )

        assert resp.status_code == 200
        assert primary["phone"] == "555-0100"


class TestContactNameTrimming:
    """Trim before validating, so whitespace can't masquerade as a name.

    POST goes through VendorContactCreateInline, which already trimmed; PATCH
    goes through VendorContactUpdate, which did not until now. Both are covered
    so the two paths can't drift apart again.
    """

    def test_create_rejects_a_whitespace_only_name(self, client_with):
        client = client_with(FakeDB([_contact(primary=True)]))

        resp = client.post(
            f"/api/v1/vendors/{VENDOR_ID}/contacts",
            json={"full_name": "   ", "email": "a@example.com"},
        )

        assert resp.status_code == 422

    def test_create_stores_a_padded_name_trimmed(self, client_with):
        fake = FakeDB([_contact(primary=True)])
        client = client_with(fake)

        resp = client.post(
            f"/api/v1/vendors/{VENDOR_ID}/contacts",
            json={"full_name": "  Dana Reed  ", "email": "dana@example.com"},
        )

        assert resp.status_code == 201
        assert resp.json()["full_name"] == "Dana Reed"

    def test_update_rejects_a_whitespace_only_name(self, client_with):
        existing = _contact(primary=True)
        client = client_with(FakeDB([existing]))

        resp = client.patch(
            f"/api/v1/vendors/{VENDOR_ID}/contacts/{existing['id']}",
            json={"full_name": "   "},
        )

        assert resp.status_code == 422

    def test_update_stores_a_padded_name_trimmed(self, client_with):
        existing = _contact(primary=True)
        fake = FakeDB([existing])
        client = client_with(fake)

        resp = client.patch(
            f"/api/v1/vendors/{VENDOR_ID}/contacts/{existing['id']}",
            json={"full_name": "  Sam Lee  "},
        )

        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Sam Lee"
