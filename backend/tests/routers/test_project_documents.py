"""Router tests for project document upload + delete hardening (Task 3.4).

Covers the two fixes: unique storage keys (a same-named re-upload no longer
collides into a 500), and the delete guard that blocks removing a document
still referenced by a bid package (scope-of-work FK or the reference pool),
returning a clean 409 instead of a raw 23503.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

_PDF_BYTES = b"%PDF-1.4\n%minimal pdf for testing\n%%EOF"

USER = {
    "user_id": str(uuid4()),
    "email": "admin@example.com",
    "full_name": "Admin",
    "role": "admin",
    "is_active": True,
}

PROJECT_ID = str(uuid4())
DOC_ID = str(uuid4())


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, fake: "FakeDB", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters: list[tuple] = []
        self._want_count = False
        self._single = False

    def select(self, *_a, count=None, **_k):
        self._op = "select"
        if count == "exact":
            self._want_count = True
        return self

    def insert(self, payload):
        self._op = "insert"
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

    def order(self, *_a, **_k):
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        return self._fake._resolve(self)


class FakeDB:
    def __init__(
        self,
        *,
        project: dict | None = None,
        document: dict | None = None,
        sow_count: int = 0,
        pool_count: int = 0,
        raise_fk_on_delete: bool = False,
    ):
        self.project = project if project is not None else {"id": PROJECT_ID, "archived_at": None}
        self.document = document
        self.sow_count = sow_count
        self.pool_count = pool_count
        self.raise_fk_on_delete = raise_fk_on_delete
        self.inserted_documents: list[dict] = []
        self.deleted_document_ids: list[str] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, q: _Query):
        if q._table == "projects" and q._op == "select":
            return _Result(self.project if q._single else [self.project])

        if q._table == "project_documents" and q._op == "select":
            return _Result(self.document if q._single else ([self.document] if self.document else []))

        if q._table == "project_documents" and q._op == "insert":
            row = {
                "id": str(uuid4()),
                "file_type": None,
                "file_size": None,
                "document_kind": "reference",
                "uploaded_at": "2026-05-25T00:00:00Z",
                **q._payload,
            }
            self.inserted_documents.append(row)
            return _Result([row])

        if q._table == "project_documents" and q._op == "delete":
            if self.raise_fk_on_delete:
                raise APIError({"code": "23503", "message": "fk", "details": None, "hint": None})
            for kind, col, val in q._filters:
                if kind == "eq" and col == "id":
                    self.deleted_document_ids.append(val)
            return _Result([])

        if q._table == "bid_packages" and q._op == "select":
            return _Result([], count=self.sow_count)

        if q._table == "bid_package_documents" and q._op == "select":
            return _Result([], count=self.pool_count)

        return _Result(None if q._single else [])


def _client_for(fake):
    app.dependency_overrides[get_current_active_user] = lambda: USER
    app.dependency_overrides[get_supabase] = lambda: fake
    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_storage_and_validation():
    with (
        patch("app.routers.projects.validate_upload"),
        patch("app.routers.projects.upload_file"),
        patch("app.routers.projects.delete_file"),
    ):
        yield


BASE = f"/api/v1/projects/{PROJECT_ID}/documents"


class TestUploadUniquify:
    def test_same_name_reupload_gets_distinct_paths(self):
        fake = FakeDB()
        try:
            client = _client_for(fake)
            files = {"file": ("plans.pdf", _PDF_BYTES, "application/pdf")}
            r1 = client.post(BASE, files=files)
            r2 = client.post(BASE, files={"file": ("plans.pdf", _PDF_BYTES, "application/pdf")})
            assert r1.status_code == 201, r1.text
            assert r2.status_code == 201, r2.text
            paths = {d["file_path"] for d in fake.inserted_documents}
            assert len(paths) == 2  # no collision, no 500
        finally:
            app.dependency_overrides.clear()


class TestDeleteGuard:
    def _doc(self):
        return {"file_path": f"{PROJECT_ID}/{uuid4().hex}/plans.pdf"}

    def test_sow_reference_blocks_with_409(self):
        fake = FakeDB(document=self._doc(), sow_count=1)
        try:
            resp = _client_for(fake).delete(f"{BASE}/{DOC_ID}")
            assert resp.status_code == 409, resp.text
            assert "scope of work" in resp.json()["detail"]
            assert fake.deleted_document_ids == []  # not deleted
        finally:
            app.dependency_overrides.clear()

    def test_reference_pool_blocks_with_409(self):
        fake = FakeDB(document=self._doc(), sow_count=0, pool_count=2)
        try:
            resp = _client_for(fake).delete(f"{BASE}/{DOC_ID}")
            assert resp.status_code == 409, resp.text
            assert "attached to a bid package" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_unreferenced_document_deletes(self):
        fake = FakeDB(document=self._doc(), sow_count=0, pool_count=0)
        try:
            resp = _client_for(fake).delete(f"{BASE}/{DOC_ID}")
            assert resp.status_code == 204, resp.text
            assert fake.deleted_document_ids == [DOC_ID]
        finally:
            app.dependency_overrides.clear()

    def test_missing_document_is_404(self):
        fake = FakeDB(document=None)
        try:
            resp = _client_for(fake).delete(f"{BASE}/{DOC_ID}")
            assert resp.status_code == 404, resp.text
        finally:
            app.dependency_overrides.clear()

    def test_fk_error_on_delete_is_translated_to_409(self):
        # Backstop: any other RESTRICT FK surfacing as 23503 becomes a clean 409.
        fake = FakeDB(document=self._doc(), sow_count=0, pool_count=0, raise_fk_on_delete=True)
        try:
            resp = _client_for(fake).delete(f"{BASE}/{DOC_ID}")
            assert resp.status_code == 409, resp.text
            assert "in use" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()
