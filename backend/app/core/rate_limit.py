"""
Simple in-memory sliding-window rate limiter for public vendor endpoints.

Scope: defense-in-depth on the magic-link validate-token endpoint. The token
itself carries ~256 bits of entropy, so brute force is infeasible — this
limiter exists mainly to blunt enumeration / DoS attempts and to surface
misconfigured clients early.

Trade-offs accepted for MVP:
  - Per-worker-process state (not cluster-wide). Acceptable because the
    global bound is a floor, not a ceiling, and a multi-worker deploy
    still caps burst per vendor.
  - No background sweep. Stale IPs are pruned lazily on each call, and
    the bucket map is bounded by unique-IPs-in-window which stays tiny.
"""

from __future__ import annotations

import time
from threading import Lock

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60.0
_MAX_REQUESTS = 10

_buckets: dict[str, list[float]] = {}
_lock = Lock()


def _client_ip(request: Request) -> str:
    """First hop in X-Forwarded-For if present, else direct peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def validate_token_rate_limit(request: Request) -> None:
    """
    FastAPI dependency — 10 requests per IP per 60s on validate-token.

    Raises 429 with Retry-After when exceeded.
    """
    ip = _client_ip(request)
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        timestamps = _buckets.get(ip, [])
        # Drop timestamps that fell out of the window.
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= _MAX_REQUESTS:
            # Opportunistic cleanup so the bucket map doesn't grow unboundedly.
            _sweep_stale(cutoff)
            _buckets[ip] = timestamps
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again.",
                headers={"Retry-After": str(int(_WINDOW_SECONDS))},
            )

        timestamps.append(now)
        _buckets[ip] = timestamps


def _sweep_stale(cutoff: float) -> None:
    """Remove IPs whose bucket is fully expired. Caller holds the lock."""
    stale = [ip for ip, ts in _buckets.items() if not ts or ts[-1] <= cutoff]
    for ip in stale:
        _buckets.pop(ip, None)
