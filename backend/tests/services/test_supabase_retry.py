"""
Fix A: the Supabase postgrest session retries once on a stale/dropped connection
(HTTP/2 GOAWAY = RemoteProtocolError, or a connect failure), so the first request
after an idle period doesn't 500.
"""

import httpx
import pytest

from app.core.supabase_client import (
    _RetryTransport,
    _install_retry_transport,
)

REQ = httpx.Request("GET", "https://example.supabase.co/rest/v1/notifications")


class _FlakyTransport(httpx.BaseTransport):
    """Raises the given exc on the first N calls, then returns 200."""

    def __init__(self, exc: Exception, fail_times: int) -> None:
        self.exc = exc
        self.fail_times = fail_times
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return httpx.Response(200, request=request)


def test_retries_once_on_remote_protocol_error():
    inner = _FlakyTransport(
        httpx.RemoteProtocolError("ConnectionTerminated", request=REQ),
        fail_times=1,
    )
    transport = _RetryTransport(inner, retries=1)
    resp = transport.handle_request(REQ)
    assert resp.status_code == 200
    assert inner.calls == 2  # failed once, succeeded on the fresh connection


def test_retries_once_on_connect_error():
    inner = _FlakyTransport(httpx.ConnectError("conn refused", request=REQ), fail_times=1)
    resp = _RetryTransport(inner, retries=1).handle_request(REQ)
    assert resp.status_code == 200
    assert inner.calls == 2


def test_reraises_after_exhausting_retries():
    inner = _FlakyTransport(
        httpx.RemoteProtocolError("ConnectionTerminated", request=REQ),
        fail_times=5,
    )
    with pytest.raises(httpx.RemoteProtocolError):
        _RetryTransport(inner, retries=1).handle_request(REQ)
    assert inner.calls == 2  # original + one retry, then gives up


def test_does_not_retry_unrelated_errors():
    inner = _FlakyTransport(httpx.ReadTimeout("slow query", request=REQ), fail_times=5)
    with pytest.raises(httpx.ReadTimeout):
        _RetryTransport(inner, retries=1).handle_request(REQ)
    assert inner.calls == 1  # not a connection error → no retry


def test_install_wraps_session_transport_idempotently():
    class _FakePostgrest:
        def __init__(self) -> None:
            self.session = httpx.Client()

    class _FakeClient:
        def __init__(self) -> None:
            self.postgrest = _FakePostgrest()

    client = _FakeClient()
    original = client.postgrest.session._transport

    _install_retry_transport(client)
    wrapped = client.postgrest.session._transport
    assert isinstance(wrapped, _RetryTransport)
    assert wrapped._inner is original

    # Idempotent: a second install doesn't double-wrap.
    _install_retry_transport(client)
    assert client.postgrest.session._transport is wrapped
