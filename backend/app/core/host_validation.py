"""Host header allow list.

Starlette rebuilds `request.url` (and with it FastAPI's trailing-slash redirect
Location) from the Host header, so an unchecked Host lets a caller point those
URLs at a domain of their choosing. With ALLOWED_HOSTS set, any other Host gets
400 before routing.

/health is exempt: the ALB target-group health check addresses the task by its
private IP, so its Host is an address that changes on every deployment. A
rejected health check would take the single API task out of service.
"""

from __future__ import annotations

from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

_EXEMPT_PATHS = frozenset({"/health"})


class HostValidationMiddleware:
    """TrustedHostMiddleware for every path except the ALB health check."""

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.checked = TrustedHostMiddleware(
            app, allowed_hosts=allowed_hosts, www_redirect=False
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        await self.checked(scope, receive, send)
