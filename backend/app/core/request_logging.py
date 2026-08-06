"""Request logging middleware: one structured line per request.

Pure ASGI rather than Starlette's BaseHTTPMiddleware. BaseHTTPMiddleware runs the
downstream app in a separate anyio task, so a ContextVar set by a dependency (the
actor stamp, see app/core/auth.py) would not be visible when the middleware
resumes. Plain ASGI awaits the app in the same context, so it is.

What is deliberately NOT logged: request headers (Authorization carries live
JWTs), request/response bodies (the vendor magic-link token arrives in the POST
body of /vendor-auth/validate-token), and query strings. Path, method, status,
duration, and actor identity are enough to trace an incident.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import actor_var, get_actor, request_id_var


logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "x-request-id"

# Upper bound on an inbound correlation id we are willing to echo. Long enough
# for a UUID or an ALB trace id, short enough that a caller cannot pad the log.
_MAX_REQUEST_ID_LENGTH = 64

# Polled continuously by infrastructure: the ALB hits /health and the external
# canary hits scheduler-health (see docs/adr/0001-scheduler-single-instance.md).
# Logged at DEBUG so they do not bury real traffic at INFO.
_QUIET_PATHS = frozenset({"/health", "/api/v1/admin/scheduler-health"})


def _sanitize_request_id(raw: str | None) -> str | None:
    """Accept a caller-supplied correlation id only if it is safe to log.

    An unvalidated header is a log-injection vector: a newline in the value lets
    a caller forge additional log lines. Rejecting also covers oversized values
    and control characters. Returns None when the value cannot be trusted, and
    the caller generates a fresh id instead.
    """
    if not raw:
        return None
    value = raw.strip()
    if not value or len(value) > _MAX_REQUEST_ID_LENGTH:
        return None
    # Printable ASCII only — excludes newlines, tabs, and control characters.
    if not all(32 <= ord(char) < 127 for char in value):
        return None
    return value


def _inbound_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.decode("latin-1").lower() == REQUEST_ID_HEADER:
            return _sanitize_request_id(value.decode("latin-1"))
    return None


def _route_template(scope: Scope) -> str | None:
    """The matched route pattern (e.g. /api/v1/vendors/{vendor_id}), if matched.

    Logged alongside the concrete path so log queries can aggregate by endpoint
    without the id cardinality. Absent on 404s, which never match a route.
    """
    route = scope.get("route")
    return getattr(route, "path_format", None) or getattr(route, "path", None)


class RequestLoggingMiddleware:
    """Assign a correlation id, time the request, and log one line on completion."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # lifespan and websocket carry no request semantics.
            await self.app(scope, receive, send)
            return

        request_id = _inbound_request_id(scope) or uuid.uuid4().hex

        # Tokens are reset in the finally below so no id or actor leaks into the
        # next request handled by this worker.
        request_id_token = request_id_var.set(request_id)
        actor_token = actor_var.set(None)

        status_code = 500  # Stands unless response.start is actually sent.
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                headers.append(
                    (REQUEST_ID_HEADER.encode("latin-1"), request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Log with the correlation id attached, then re-raise so Starlette's
            # error handling is unchanged.
            logger.exception(
                "%s %s failed",
                scope.get("method", "-"),
                scope.get("path", "-"),
                extra=self._fields(scope, status=500, started=started),
            )
            raise
        else:
            path = scope.get("path", "")
            # Demote the constantly-polled health endpoints to DEBUG, but only
            # while they are actually healthy. A failing health check is exactly
            # the thing we must not silence.
            quiet = path in _QUIET_PATHS and status_code < 400
            level = logging.DEBUG if quiet else logging.INFO
            logger.log(
                level,
                "%s %s %s",
                scope.get("method", "-"),
                path,
                status_code,
                extra=self._fields(scope, status=status_code, started=started),
            )
        finally:
            request_id_var.reset(request_id_token)
            actor_var.reset(actor_token)

    @staticmethod
    def _fields(scope: Scope, *, status: int, started: float) -> dict:
        fields = {
            # Also stamped onto every record by ContextFilter. Set explicitly
            # here so the request line carries it even through a handler that
            # was configured without the filter (pytest's caplog, for one).
            "request_id": request_id_var.get(""),
            "method": scope.get("method", "-"),
            # scope["path"] excludes the query string by construction, so no
            # token or filter value can ride along into the logs.
            "path": scope.get("path", "-"),
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        route = _route_template(scope)
        if route:
            fields["route"] = route
        # Set by the auth dependencies once identity is established. Absent for
        # unauthenticated routes (health, webhooks, magic-link validation).
        fields.update(get_actor())
        return fields
