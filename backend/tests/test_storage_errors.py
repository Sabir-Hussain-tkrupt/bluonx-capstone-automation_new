"""Unit tests for storage-layer error mapping in `upload_file`.

The bug this covers: a bare `except Exception` turned every storage failure
into a 500, including the ones where the storage API had already said exactly
what was wrong ("mime type X is not supported"). A caller error read as an
outage, and the reason was thrown away.

`StorageApiError` is not a `postgrest.APIError`, so the global handler in
`app.core.db_errors` never sees it. The mapping has to live here, which is why
these tests exercise `upload_file` directly rather than through a router. The
three upload call sites (projects, vendors, vendor_portal) all call it bare,
with no local `except`, so whatever it raises is what the client gets.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException
from storage3.exceptions import StorageApiError

from app.core.storage import upload_file

BUCKET = "project-documents"
PATH = "some-project/abc123/plans.docx"
CONTENT = b"PK\x03\x04 pretend docx"
CTYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _FakeBucket:
    def __init__(self, error: BaseException | None):
        self._error = error
        self.calls: list[tuple] = []

    def upload(self, path, file_bytes, options):
        self.calls.append((path, file_bytes, options))
        if self._error is not None:
            raise self._error
        return {"path": path}


class _FakeStorage:
    def __init__(self, bucket: _FakeBucket):
        self._bucket = bucket

    def from_(self, _name):
        return self._bucket


class FakeClient:
    """Minimal stand-in for supabase.Client covering `.storage.from_().upload()`."""

    def __init__(self, error: BaseException | None = None):
        self.bucket = _FakeBucket(error)
        self.storage = _FakeStorage(self.bucket)


def _upload(client: FakeClient):
    return upload_file(client, BUCKET, PATH, CONTENT, CTYPE)


class TestRejectionsAreNot500:
    def test_unsupported_mime_type_maps_to_415_with_reason(self):
        """The original defect: a bucket MIME list narrower than the app's."""
        # `.status` arrives off the wire as a *str*, which is how storage3
        # constructs it. The coercion in upload_file has to handle that.
        exc = StorageApiError(
            "mime type application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document is not supported",
            "invalid_mime_type",
            "415",
        )
        with pytest.raises(HTTPException) as raised:
            _upload(FakeClient(exc))

        assert raised.value.status_code == 415
        assert "not supported" in raised.value.detail
        assert "mime type" in raised.value.detail

    def test_payload_too_large_maps_to_413(self):
        exc = StorageApiError("The object exceeded the maximum allowed size", "Payload too large", 413)
        with pytest.raises(HTTPException) as raised:
            _upload(FakeClient(exc))

        assert raised.value.status_code == 413
        assert "maximum allowed size" in raised.value.detail

    def test_duplicate_object_maps_to_409(self):
        exc = StorageApiError("The resource already exists", "Duplicate", "409")
        with pytest.raises(HTTPException) as raised:
            _upload(FakeClient(exc))

        assert raised.value.status_code == 409

    def test_unmapped_4xx_degrades_to_400_not_500(self):
        exc = StorageApiError("Invalid key: bad//path", "InvalidKey", "422")
        with pytest.raises(HTTPException) as raised:
            _upload(FakeClient(exc))

        assert raised.value.status_code == 400
        assert "Invalid key" in raised.value.detail

    def test_rejection_is_logged_at_warning_not_error(self, caplog):
        """A caller error is not an outage, so it must not page as one."""
        exc = StorageApiError("mime type text/plain is not supported", "invalid_mime_type", "415")
        with caplog.at_level(logging.WARNING, logger="app.core.storage"):
            with pytest.raises(HTTPException):
                _upload(FakeClient(exc))

        records = [r for r in caplog.records if r.name == "app.core.storage"]
        assert records, "expected a log record from app.core.storage"
        assert all(r.levelno == logging.WARNING for r in records)
        assert "invalid_mime_type" in caplog.text


class TestRealFailuresStay500:
    def test_storage_5xx_is_500_generic_and_logged(self, caplog):
        exc = StorageApiError("upstream connect error", "InternalError", "503")
        with caplog.at_level(logging.ERROR, logger="app.core.storage"):
            with pytest.raises(HTTPException) as raised:
                _upload(FakeClient(exc))

        assert raised.value.status_code == 500
        assert raised.value.detail == "Failed to upload file to storage."
        # Nothing from the driver leaks into the body, but the cause is logged.
        assert "upstream connect error" in caplog.text

    def test_network_error_is_500_generic_and_logged(self, caplog):
        exc = ConnectionError("connection reset by peer")
        with caplog.at_level(logging.ERROR, logger="app.core.storage"):
            with pytest.raises(HTTPException) as raised:
                _upload(FakeClient(exc))

        assert raised.value.status_code == 500
        assert raised.value.detail == "Failed to upload file to storage."
        assert "connection reset by peer" in caplog.text

    def test_unparseable_status_falls_through_to_500(self):
        """A malformed `.status` must not be mistaken for a client rejection."""
        exc = StorageApiError("something odd", "InternalError", "not-a-number")
        with pytest.raises(HTTPException) as raised:
            _upload(FakeClient(exc))

        assert raised.value.status_code == 500


class TestSuccessPathUnchanged:
    def test_returns_path_and_forwards_content_type(self):
        client = FakeClient()
        assert _upload(client) == PATH
        path, body, options = client.bucket.calls[0]
        assert path == PATH
        assert body == CONTENT
        assert options == {"content-type": CTYPE}
