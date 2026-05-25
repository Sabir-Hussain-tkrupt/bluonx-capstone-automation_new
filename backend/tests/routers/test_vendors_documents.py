"""Router-level tests for vendor document upload/delete (Task 7.4.5).

Focuses on the recompute wiring added to upload_vendor_document and
delete_vendor_document. The recompute helper itself is unit-tested in
backend/tests/services/test_vendor_insurance_sync.py; here we patch it
and only verify call shape and error-surfacing behavior.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app


# Minimal valid PDF — passes the magic-byte check in file_validation.py
_PDF_BYTES = b"%PDF-1.4\n%minimal pdf for testing\n%%EOF"


USER = {
    "user_id": str(uuid4()),
    "email": "admin@example.com",
    "full_name": "Admin",
    "role": "admin",
    "is_active": True,
}


# ── Fake supabase that handles the chains hit by the upload/delete paths ─


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, fake: "FakeDB", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters: list[tuple] = []
        self._single = False

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        return self._fake._resolve(self)


class FakeDB:
    """Minimal supabase double for vendor document upload/delete chains."""

    def __init__(
        self,
        *,
        vendor_exists: bool = True,
        existing_doc: dict | None = None,
    ):
        self.vendor_exists = vendor_exists
        self.existing_doc = existing_doc
        self.inserted_documents: list[dict] = []
        self.deleted_document_ids: list[str] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, q: _Query):
        if q._table == "vendors" and q._op == "select":
            if self.vendor_exists:
                return _Result({"id": "v"} if q._single else [{"id": "v"}])
            return _Result(None if q._single else [])

        if q._table == "vendor_documents" and q._op == "insert":
            row = dict(q._payload)
            row.setdefault("id", str(uuid4()))
            row.setdefault("uploaded_at", "2026-05-25T00:00:00Z")
            row.setdefault("updated_at", "2026-05-25T00:00:00Z")
            self.inserted_documents.append(row)
            return _Result([row])

        if q._table == "vendor_documents" and q._op == "select":
            if self.existing_doc:
                return _Result(
                    self.existing_doc if q._single else [self.existing_doc]
                )
            return _Result(None if q._single else [])

        if q._table == "vendor_documents" and q._op == "delete":
            for kind, col, val in q._filters:
                if kind == "eq" and col == "id":
                    self.deleted_document_ids.append(val)
            return _Result([])

        return _Result(None if q._single else [])


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def fake_db():
    return FakeDB()


@pytest.fixture()
def client_with(fake_db):
    app.dependency_overrides[get_current_active_user] = lambda: USER
    app.dependency_overrides[get_supabase] = lambda: fake_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _patch_storage_and_validation():
    """Patch the storage/validation helpers used by upload_vendor_document
    so the tests don't need a real Supabase Storage backend."""
    with (
        patch("app.routers.vendors.validate_upload"),
        patch("app.routers.vendors.upload_file"),
        patch("app.routers.vendors.delete_file"),
    ):
        yield


def _upload(client, vendor_id: str, *, document_type: str, expiration_date: str | None):
    files = {"file": ("cert.pdf", _PDF_BYTES, "application/pdf")}
    data = {"document_type": document_type}
    if expiration_date is not None:
        data["expiration_date"] = expiration_date
    return client.post(
        f"/api/v1/vendors/{vendor_id}/documents", files=files, data=data
    )


# ── Upload ───────────────────────────────────────────────────────────────


class TestUploadVendorDocument:
    def test_insurance_cert_triggers_recompute(self, client_with, fake_db):
        vendor_id = str(uuid4())
        with patch(
            "app.routers.vendors.recompute_vendor_insurance_expiration"
        ) as recompute:
            resp = _upload(
                client_with,
                vendor_id,
                document_type="insurance_certificate",
                expiration_date="2027-01-01",
            )
        assert resp.status_code == 201, resp.text
        assert len(fake_db.inserted_documents) == 1
        recompute.assert_called_once()
        called_db, called_vendor_id = recompute.call_args.args
        assert called_db is fake_db
        assert str(called_vendor_id) == vendor_id

    def test_non_insurance_upload_does_not_recompute(self, client_with, fake_db):
        vendor_id = str(uuid4())
        with patch(
            "app.routers.vendors.recompute_vendor_insurance_expiration"
        ) as recompute:
            resp = _upload(
                client_with, vendor_id, document_type="w9", expiration_date=None
            )
        assert resp.status_code == 201, resp.text
        recompute.assert_not_called()

    def test_recompute_failure_surfaces_500(self, client_with, fake_db):
        vendor_id = str(uuid4())
        with patch(
            "app.routers.vendors.recompute_vendor_insurance_expiration",
            side_effect=RuntimeError("boom"),
        ):
            resp = _upload(
                client_with,
                vendor_id,
                document_type="insurance_certificate",
                expiration_date="2027-01-01",
            )
        assert resp.status_code == 500
        assert resp.json()["detail"] == (
            "Document saved, but the vendor's insurance date may not have "
            "updated. Please refresh and check the vendor record."
        )
        # The vendor_documents row was already inserted before recompute ran.
        assert len(fake_db.inserted_documents) == 1


# ── Delete ───────────────────────────────────────────────────────────────


class TestDeleteVendorDocument:
    def test_delete_insurance_cert_recomputes(self):
        vendor_id = str(uuid4())
        document_id = str(uuid4())
        fake = FakeDB(
            existing_doc={
                "file_path": f"{vendor_id}/insurance_certificate/cert.pdf",
                "document_type": "insurance_certificate",
            }
        )
        app.dependency_overrides[get_current_active_user] = lambda: USER
        app.dependency_overrides[get_supabase] = lambda: fake
        try:
            client = TestClient(app)
            with patch(
                "app.routers.vendors.recompute_vendor_insurance_expiration"
            ) as recompute:
                resp = client.delete(
                    f"/api/v1/vendors/{vendor_id}/documents/{document_id}"
                )
            assert resp.status_code == 204, resp.text
            recompute.assert_called_once()
            assert fake.deleted_document_ids == [document_id]
        finally:
            app.dependency_overrides.clear()

    def test_delete_non_insurance_does_not_recompute(self):
        vendor_id = str(uuid4())
        document_id = str(uuid4())
        fake = FakeDB(
            existing_doc={
                "file_path": f"{vendor_id}/w9/w9.pdf",
                "document_type": "w9",
            }
        )
        app.dependency_overrides[get_current_active_user] = lambda: USER
        app.dependency_overrides[get_supabase] = lambda: fake
        try:
            client = TestClient(app)
            with patch(
                "app.routers.vendors.recompute_vendor_insurance_expiration"
            ) as recompute:
                resp = client.delete(
                    f"/api/v1/vendors/{vendor_id}/documents/{document_id}"
                )
            assert resp.status_code == 204, resp.text
            recompute.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    def test_delete_recompute_failure_surfaces_500(self):
        vendor_id = str(uuid4())
        document_id = str(uuid4())
        fake = FakeDB(
            existing_doc={
                "file_path": f"{vendor_id}/insurance_certificate/cert.pdf",
                "document_type": "insurance_certificate",
            }
        )
        app.dependency_overrides[get_current_active_user] = lambda: USER
        app.dependency_overrides[get_supabase] = lambda: fake
        try:
            client = TestClient(app)
            with patch(
                "app.routers.vendors.recompute_vendor_insurance_expiration",
                side_effect=RuntimeError("boom"),
            ):
                resp = client.delete(
                    f"/api/v1/vendors/{vendor_id}/documents/{document_id}"
                )
            assert resp.status_code == 500
            assert resp.json()["detail"] == (
                "Document deleted, but the vendor's insurance date may not "
                "have updated. Please refresh and check the vendor record."
            )
            # The vendor_documents row was already deleted before recompute ran.
            assert fake.deleted_document_ids == [document_id]
        finally:
            app.dependency_overrides.clear()
