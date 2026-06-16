"""
Global Supabase admin client (service_role key).

Created once in FastAPI lifespan, injected via Depends().
Safe for concurrent async requests — httpx.AsyncClient is task-safe
and the service_role key is stateless (no session bleed).

Stale-connection resilience (Fix A): the client is a long-lived singleton whose
postgrest httpx session keeps HTTP/2 connections alive. Supabase's edge sends a
graceful GOAWAY (RemoteProtocolError, error_code 0) on idle connections; the next
request can grab that now-dead pooled connection and fail with a 500 before httpx
dials a fresh one. We wrap the session's transport so such a request retries once
on a new connection. Only connection-level, pre-processing errors are retried
(GOAWAY / connect failure), so retrying a write never double-applies it.
"""

import logging

import httpx
from fastapi import Request
from supabase import Client, create_client

logger = logging.getLogger(__name__)

# Module-level singleton. Populated by init_supabase() at app startup so
# non-request contexts (background jobs) can reach the client without a Request.
_client: Client | None = None

# Errors that mean the connection died before the server processed the request,
# so retrying on a fresh connection is safe (including for writes).
_RETRYABLE_TRANSPORT_ERRORS = (httpx.RemoteProtocolError, httpx.ConnectError)


class _RetryTransport(httpx.BaseTransport):
    """Delegates to the real transport, retrying once on a stale/dropped
    connection. httpx evicts the failed connection, so the retry dials fresh."""

    def __init__(self, inner: httpx.BaseTransport, retries: int = 1) -> None:
        self._inner = inner
        self._retries = retries

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                return self._inner.handle_request(request)
            except _RETRYABLE_TRANSPORT_ERRORS as exc:
                last_exc = exc
                if attempt < self._retries:
                    logger.warning(
                        "Supabase request hit a stale connection (%s); retrying "
                        "on a fresh connection (%d/%d)",
                        type(exc).__name__,
                        attempt + 1,
                        self._retries,
                    )
        assert last_exc is not None  # only reached after exhausting retries
        raise last_exc

    def close(self) -> None:
        self._inner.close()


def _install_retry_transport(client: Client) -> None:
    """Wrap the postgrest session's transport with _RetryTransport (idempotent).

    Best-effort: if the supabase-py/httpx internals differ, log and continue —
    the client still works, just without the retry shim.
    """
    try:
        session = client.postgrest.session  # httpx.Client
        inner = session._transport
        if not isinstance(inner, _RetryTransport):
            session._transport = _RetryTransport(inner)
    except Exception:  # noqa: BLE001 — never let the shim break startup
        logger.exception("Could not install Supabase retry transport; continuing")


def init_supabase(url: str, service_role_key: str) -> Client:
    """Create the global Supabase client. Called once in FastAPI lifespan."""
    global _client
    _client = create_client(url, service_role_key)
    _install_retry_transport(_client)
    return _client


def get_supabase(request: Request) -> Client:
    """FastAPI dependency — injects the global Supabase client from app.state."""
    return request.app.state.supabase


def get_supabase_client() -> Client:
    """Module-level accessor for non-request contexts (e.g. scheduled jobs)."""
    if _client is None:
        raise RuntimeError("Supabase client not initialized")
    return _client
