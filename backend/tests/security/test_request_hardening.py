"""
Request-level DoS hardening (October 2026 security remediation).

Covers the body-size limit (app/core/body_limit.py), the Host allow list
(app/core/host_validation.py), the X-Forwarded-For client IP used by the rate
limiter, and the chunked upload reader. No database: the oversized requests are
all refused before routing or auth, which is the point.
"""

import io
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.body_limit import DEFAULT_MAX_BODY_BYTES, max_body_bytes
from app.core.file_validation import read_upload
from app.core.host_validation import HostValidationMiddleware
from app.core.rate_limit import client_ip
from app.main import app

MB = 1024 * 1024

PROJECT_UPLOAD = f"/api/v1/projects/{uuid4()}/documents"
VENDOR_UPLOAD = f"/api/v1/vendors/{uuid4()}/documents"
ATTACHMENT_UPLOAD = f"/api/v1/vendor-portal/submissions/{uuid4()}/attachments"


@pytest.fixture()
def client() -> TestClient:
    # No `with`: the lifespan (Supabase client, scheduler) is not needed for
    # requests that never reach a handler.
    return TestClient(app)


def _chunks(total: int, size: int = MB):
    sent = 0
    while sent < total:
        n = min(size, total - sent)
        sent += n
        yield b"x" * n


# ── Per-route limits ────────────────────────────────────────────────────────


class TestLimitSelection:
    def test_upload_routes_get_their_file_limit_plus_overhead(self):
        assert max_body_bytes("POST", PROJECT_UPLOAD) == 51 * MB
        assert max_body_bytes("POST", VENDOR_UPLOAD) == 51 * MB
        assert max_body_bytes("POST", ATTACHMENT_UPLOAD) == 11 * MB

    def test_everything_else_gets_the_default(self):
        assert max_body_bytes("POST", "/api/v1/vendors/import") == DEFAULT_MAX_BODY_BYTES
        assert max_body_bytes("POST", "/api/v1/webhooks/ses-notifications") == DEFAULT_MAX_BODY_BYTES
        # Upload limit is POST-only.
        assert max_body_bytes("PUT", PROJECT_UPLOAD) == DEFAULT_MAX_BODY_BYTES


# ── Oversized bodies are refused without auth ───────────────────────────────


class TestDeclaredLengthRejected:
    """A Content-Length over the limit is answered 413 before the app runs."""

    @pytest.mark.parametrize(
        "path, size",
        [
            (PROJECT_UPLOAD, 52 * MB),
            (VENDOR_UPLOAD, 52 * MB),
            (ATTACHMENT_UPLOAD, 12 * MB),
            ("/api/v1/webhooks/docusign-connect", 3 * MB),
            ("/api/v1/webhooks/ses-notifications", 3 * MB),
            ("/api/v1/vendors/import", 3 * MB),
        ],
    )
    def test_oversized_anonymous_request_gets_413(self, client, path, size):
        resp = client.post(
            path,
            content=b"x" * size,
            headers={"content-type": "multipart/form-data; boundary=x"},
        )
        assert resp.status_code == 413
        assert "limit" in resp.json()["detail"]

    def test_413_carries_cors_headers(self, client):
        """CORS wraps the limiter, so a browser can read the 413."""
        resp = client.post(
            "/api/v1/vendors/import",
            content=b"x" * (3 * MB),
            headers={"origin": "http://localhost:5173", "content-type": "application/json"},
        )
        assert resp.status_code == 413
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestStreamedBodyRejected:
    """A chunked body with no Content-Length is counted as it arrives."""

    def test_chunked_upload_over_limit_gets_413(self, client):
        resp = client.post(
            ATTACHMENT_UPLOAD,
            content=_chunks(12 * MB),
            headers={"content-type": "multipart/form-data; boundary=x"},
        )
        assert resp.status_code == 413

    def test_chunked_webhook_over_limit_gets_413(self, client):
        resp = client.post(
            "/api/v1/webhooks/docusign-connect",
            content=_chunks(3 * MB),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 413


class TestNormalRequestsUnaffected:
    def test_small_anonymous_upload_still_reaches_auth(self, client):
        """Under the limit, the request proceeds as before and auth rejects it."""
        resp = client.post(
            PROJECT_UPLOAD,
            files={"file": ("a.pdf", b"%PDF-1.4 small", "application/pdf")},
        )
        assert resp.status_code == 401


# ── Host allow list ─────────────────────────────────────────────────────────


@pytest.fixture()
def host_client() -> TestClient:
    mini = FastAPI()

    @mini.get("/health")
    def health():
        return {"ok": True}

    @mini.get("/api/v1/thing")
    def thing():
        return {"ok": True}

    mini.add_middleware(HostValidationMiddleware, allowed_hosts=["api.bluonx.com"])
    return TestClient(mini)


class TestHostValidation:
    def test_allowed_host_passes(self, host_client):
        resp = host_client.get("/api/v1/thing", headers={"host": "api.bluonx.com"})
        assert resp.status_code == 200

    def test_foreign_host_rejected(self, host_client):
        resp = host_client.get("/api/v1/thing", headers={"host": "evil.example.com"})
        assert resp.status_code == 400

    def test_health_reachable_by_private_ip(self, host_client):
        """The ALB health check addresses the task by IP."""
        resp = host_client.get("/health", headers={"host": "10.0.3.17:8000"})
        assert resp.status_code == 200


# ── Client IP for rate limiting ─────────────────────────────────────────────


def _request(xff: str | None, peer: str = "10.0.0.5") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


class TestClientIp:
    def test_uses_last_hop_appended_by_alb(self):
        """A client-supplied first entry must not choose the rate-limit key."""
        assert client_ip(_request("1.2.3.4, 198.51.100.7")) == "198.51.100.7"

    def test_single_entry(self):
        assert client_ip(_request("198.51.100.7")) == "198.51.100.7"

    def test_falls_back_to_peer(self):
        assert client_ip(_request(None)) == "10.0.0.5"


# ── Chunked upload reader ───────────────────────────────────────────────────


class TestReadUpload:
    async def test_reads_file_under_limit(self):
        data = b"a" * (3 * MB + 17)
        upload = UploadFile(file=io.BytesIO(data), filename="a.pdf")
        assert await read_upload(upload, "bid-attachments") == data

    async def test_stops_at_first_chunk_over_limit(self):
        stream = io.BytesIO(b"a" * (20 * MB))
        upload = UploadFile(file=stream, filename="a.pdf")
        with pytest.raises(HTTPException) as exc:
            await read_upload(upload, "bid-attachments")
        assert exc.value.status_code == 422
        assert exc.value.detail == "File exceeds the 10MB size limit."
        # Stopped just past 10MB, not after loading all 20MB.
        assert stream.tell() <= 11 * MB
