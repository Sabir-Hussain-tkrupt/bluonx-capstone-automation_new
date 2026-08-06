"""RequestLoggingMiddleware: correlation ids, log shape, and redaction.

The middleware is the production trace: without it an incident has no way to tie
an error to a request or a caller. These tests pin the pieces that make that
work, plus the two things that must NEVER appear in a log line (query strings,
which can carry filter values and tokens, and forged correlation ids).
"""

from __future__ import annotations

import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.logging_config import request_id_var
from app.core.request_logging import (
    REQUEST_ID_HEADER,
    RequestLoggingMiddleware,
    _sanitize_request_id,
)
from app.core.supabase_client import get_supabase_client


class TestCorrelationId:
    def test_response_carries_a_generated_request_id(self, tiny_client):
        resp = tiny_client.get("/ping")
        assert resp.status_code == 200
        assert resp.headers[REQUEST_ID_HEADER]

    def test_each_request_gets_a_distinct_id(self, tiny_client):
        first = tiny_client.get("/ping").headers[REQUEST_ID_HEADER]
        second = tiny_client.get("/ping").headers[REQUEST_ID_HEADER]
        assert first != second

    def test_valid_inbound_id_is_reused(self, tiny_client):
        # Lets a load balancer or upstream service stitch its trace to ours.
        resp = tiny_client.get("/ping", headers={REQUEST_ID_HEADER: "upstream-trace-123"})
        assert resp.headers[REQUEST_ID_HEADER] == "upstream-trace-123"

    def test_logged_id_matches_the_response_header(self, tiny_client, request_records):
        resp = tiny_client.get("/ping")
        assert request_records()[0].request_id == resp.headers[REQUEST_ID_HEADER]

    def test_id_is_reset_between_requests(self, tiny_client):
        tiny_client.get("/ping")
        # Nothing may leak into the next unit of work on this worker.
        assert request_id_var.get("") == ""


class TestInboundIdIsNotTrusted:
    """A caller-supplied id is echoed into logs, so it is a log-injection vector."""

    @pytest.mark.parametrize(
        "forged",
        [
            pytest.param("abc\ndef", id="newline"),
            pytest.param("abc\r\nINFO forged line", id="crlf-forged-line"),
            pytest.param("abc\tdef", id="tab"),
            pytest.param("x" * 65, id="over-length"),
            pytest.param("   ", id="whitespace-only"),
        ],
    )
    def test_unsafe_inbound_id_is_replaced(self, tiny_client, forged):
        resp = tiny_client.get("/ping", headers={REQUEST_ID_HEADER: forged})
        returned = resp.headers[REQUEST_ID_HEADER]
        assert returned != forged
        # Replaced with a freshly generated uuid4 hex.
        assert len(returned) == 32 and returned.isalnum()

    @pytest.mark.parametrize(
        "forged",
        [
            pytest.param("héllo", id="non-ascii-latin1"),
            pytest.param("abc\x00def", id="null-byte"),
            pytest.param("abc\x1bdef", id="escape-sequence"),
            pytest.param(None, id="absent"),
            pytest.param("", id="empty"),
        ],
    )
    def test_sanitizer_rejects_values_httpx_will_not_even_send(self, forged):
        # httpx refuses to put a non-ASCII or control byte in a header, so these
        # cannot be driven through the TestClient. A real HTTP server hands the
        # raw latin-1 bytes straight to us, so the guard still has to hold.
        assert _sanitize_request_id(forged) is None

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("upstream-trace-123", id="plain"),
            pytest.param("x" * 64, id="at-the-length-limit"),
            pytest.param("Root=1-63441c4a-abcdef012345678912345678", id="alb-trace-id"),
        ],
    )
    def test_sanitizer_accepts_safe_values(self, value):
        assert _sanitize_request_id(value) == value


class TestLogLineShape:
    def test_request_line_carries_the_expected_fields(self, tiny_client, request_records):
        tiny_client.get("/ping")
        record = request_records()[0]

        assert record.method == "GET"
        assert record.path == "/ping"
        assert record.status == 200
        assert isinstance(record.duration_ms, float)
        assert record.request_id

    def test_route_template_is_logged_alongside_the_concrete_path(
        self, tiny_client, request_records
    ):
        # The template lets log queries aggregate by endpoint without the id
        # cardinality blowing the group-by apart.
        tiny_client.get("/items/abc-123")
        record = request_records()[0]

        assert record.path == "/items/abc-123"
        assert record.route == "/items/{item_id}"

    def test_exactly_one_line_per_request(self, tiny_client, request_records):
        tiny_client.get("/ping")
        assert len(request_records()) == 1


class TestRedaction:
    def test_query_string_is_never_logged(self, tiny_client, request_records):
        # Query strings can carry filter values and, historically, tokens.
        tiny_client.get("/ping?token=super-secret&page=2")
        record = request_records()[0]

        assert record.path == "/ping"
        assert "super-secret" not in record.getMessage()
        assert "super-secret" not in str(record.__dict__)

    def test_authorization_header_is_never_logged(self, tiny_client, request_records):
        tiny_client.get("/ping", headers={"Authorization": "Bearer live-jwt-value"})
        assert "live-jwt-value" not in str(request_records()[0].__dict__)


class TestQuietPaths:
    def test_health_is_logged_at_debug(self, tiny_client, request_records):
        # The ALB polls this constantly; at INFO it would bury real traffic.
        tiny_client.get("/health")
        assert request_records()[0].levelno == logging.DEBUG

    def test_scheduler_health_is_logged_at_debug(self, tiny_client, request_records):
        # Polled by the external canary per ADR 0001.
        tiny_client.get("/api/v1/admin/scheduler-health")
        assert request_records()[0].levelno == logging.DEBUG

    def test_normal_route_is_logged_at_info(self, tiny_client, request_records):
        tiny_client.get("/ping")
        assert request_records()[0].levelno == logging.INFO

    def test_failing_health_check_is_not_silenced(self, tiny_client, request_records):
        # The whole point of a health endpoint is that its failures are loud.
        # Demoting to DEBUG must be conditional on it actually being healthy.
        tiny_client.get("/api/v1/admin/scheduler-health?fail=true")
        record = request_records()[0]

        assert record.status == 503
        assert record.levelno == logging.INFO


class TestUnhandledException:
    def test_exception_is_logged_with_traceback_and_reraised(
        self, tiny_client, request_records
    ):
        with pytest.raises(RuntimeError, match="kaboom"):
            tiny_client.get("/boom")

        record = request_records()[0]
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert record.request_id
        assert record.path == "/boom"


class TestActorAttribution:
    """Proves the set_actor contextvar written inside an auth dependency is
    visible to the middleware after the endpoint returns.

    This is the load-bearing assumption behind using pure ASGI middleware
    instead of BaseHTTPMiddleware, so it is worth a real end-to-end assertion
    against the live auth dependency rather than a mock.
    """

    @pytest.fixture
    def authed_client(self, client) -> TestClient:
        # Depends on the session `client` fixture purely for its side effect:
        # it runs app.main's lifespan, which calls init_supabase() and populates
        # the module-level singleton that get_supabase() resolves from app.state.
        app = FastAPI()
        app.state.supabase = get_supabase_client()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/whoami")
        async def whoami(user: dict = Depends(get_current_active_user)):
            return {"user_id": user["user_id"]}

        return TestClient(app)

    @pytest.mark.requires_db
    def test_authenticated_request_logs_the_actor(
        self, authed_client, auth_headers, request_records
    ):
        resp = authed_client.get("/whoami", headers=auth_headers)
        assert resp.status_code == 200

        record = request_records()[0]
        assert record.user_id == resp.json()["user_id"]
        assert record.role in ("admin", "project_manager")

    def test_unauthenticated_request_has_no_actor_fields(
        self, tiny_client, request_records
    ):
        tiny_client.get("/ping")
        record = request_records()[0]
        assert not hasattr(record, "user_id")
        assert not hasattr(record, "role")

    @pytest.mark.requires_db
    def test_actor_does_not_leak_into_the_next_request(
        self, authed_client, auth_headers, request_records
    ):
        authed_client.get("/whoami", headers=auth_headers)
        authed_client.get("/whoami")  # no credentials -> 403 from HTTPBearer

        second = request_records()[1]
        assert not hasattr(second, "user_id")
