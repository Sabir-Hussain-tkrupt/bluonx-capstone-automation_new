"""Request body size limit middleware.

Nothing in front of the app bounds a request body: the ALB forwards any size,
and uvicorn and Starlette read whatever arrives. FastAPI also parses a form or
JSON body BEFORE running the auth dependencies, so an anonymous caller could
make the single API task parse an arbitrarily large upload just to be told 401
at the end. This middleware caps the body per route before any of that work.

Two checks, both answered with 413:
  - A declared Content-Length over the limit is rejected before the app runs.
  - A chunked (or under-declared) body is counted as it streams; the read that
    crosses the limit raises, which FastAPI's body parsing re-raises as is and
    a raw `await request.body()` (the webhooks) surfaces through the normal
    HTTPException handler.

Pure ASGI for the same reason as RequestLoggingMiddleware: no extra task, and
the receive channel can be wrapped without buffering the body.
"""

from __future__ import annotations

import json
import re

from fastapi import HTTPException, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

_MB = 1024 * 1024

# Room for the multipart envelope (boundaries, part headers, the small form
# fields sent alongside the file) on top of the file-size limit the endpoint
# itself enforces with a precise message.
_MULTIPART_OVERHEAD = 1 * _MB

# Every body that is not one of the uploads below: JSON APIs and the two
# webhooks. The largest legitimate one is the 100-row vendor CSV import, which
# is far below this.
DEFAULT_MAX_BODY_BYTES = 2 * _MB

# (method, path pattern, limit). Matched against the raw path because routing
# has not happened yet at this layer. Keep the file-size numbers in step with
# BUCKET_CONFIGS (app/core/file_validation.py) and MAX_ATTACHMENT_BYTES
# (app/routers/vendor_portal.py).
_V1 = re.escape(settings.API_V1_PREFIX)
_UPLOAD_LIMITS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("POST", re.compile(rf"^{_V1}/projects/[^/]+/documents/?$"), 50 * _MB + _MULTIPART_OVERHEAD),
    ("POST", re.compile(rf"^{_V1}/vendors/[^/]+/documents/?$"), 50 * _MB + _MULTIPART_OVERHEAD),
    (
        "POST",
        re.compile(rf"^{_V1}/vendor-portal/submissions/[^/]+/attachments/?$"),
        10 * _MB + _MULTIPART_OVERHEAD,
    ),
)


def max_body_bytes(method: str, path: str) -> int:
    """The body-size limit for a request, by method and raw path."""
    for route_method, pattern, limit in _UPLOAD_LIMITS:
        if method == route_method and pattern.match(path):
            return limit
    return DEFAULT_MAX_BODY_BYTES


def _too_large_detail(limit: int) -> str:
    return f"Request body exceeds the {limit / _MB:.0f}MB limit."


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodySizeLimitMiddleware:
    """Reject request bodies over the per-route limit with 413."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = max_body_bytes(scope.get("method", ""), scope.get("path", ""))

        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await self._reject(send, limit)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=_too_large_detail(limit),
                    )
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _reject(send: Send, limit: int) -> None:
        body = json.dumps({"detail": _too_large_detail(limit)}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status.HTTP_413_CONTENT_TOO_LARGE,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                    # The rest of the oversized body is never read, so the
                    # connection cannot be reused for another request.
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
