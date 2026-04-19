"""
Vendor portal authentication — completely separate from admin Supabase auth.

The vendor JWT is a custom HS256 token signed with VENDOR_JWT_SECRET. It is
issued by the magic-link validation endpoint (Task 5.2) and consumed by all
/vendor-portal/* endpoints (Tasks 5.3–5.5) via the `get_vendor_context`
dependency.

Why it is isolated from app/core/auth.py:
  - Different secret (VENDOR_JWT_SECRET vs SUPABASE_JWT_SECRET)
  - Different payload shape (vendor_id / invitation_id instead of sub/email)
  - Every vendor token carries `type: "vendor_portal"`; the dependency rejects
    any token that lacks it. So even if the two secrets were ever confused,
    an admin JWT could not satisfy a vendor-protected endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

VENDOR_TOKEN_TYPE = "vendor_portal"
VENDOR_JWT_ALGORITHM = "HS256"

_vendor_bearer_scheme = HTTPBearer(auto_error=True)


@dataclass(frozen=True)
class VendorContext:
    """Identity + scope derived from a validated vendor JWT."""

    vendor_id: UUID
    vendor_contact_id: UUID
    bid_invitation_id: UUID
    bid_package_id: UUID
    task_id: UUID


def issue_vendor_jwt(ctx: VendorContext) -> str:
    """Sign a short-lived vendor JWT for the given context."""
    now = datetime.now(timezone.utc)
    payload = {
        "type": VENDOR_TOKEN_TYPE,
        "vendor_id": str(ctx.vendor_id),
        "vendor_contact_id": str(ctx.vendor_contact_id),
        "bid_invitation_id": str(ctx.bid_invitation_id),
        "bid_package_id": str(ctx.bid_package_id),
        "task_id": str(ctx.task_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.VENDOR_JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.VENDOR_JWT_SECRET, algorithm=VENDOR_JWT_ALGORITHM)


def _decode_vendor_jwt(token: str) -> dict:
    return jwt.decode(
        token,
        settings.VENDOR_JWT_SECRET,
        algorithms=[VENDOR_JWT_ALGORITHM],
    )


async def get_vendor_context(
    credentials: HTTPAuthorizationCredentials = Depends(_vendor_bearer_scheme),
) -> VendorContext:
    """FastAPI dependency: validate vendor JWT → VendorContext."""
    try:
        payload = _decode_vendor_jwt(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Vendor JWT validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if payload.get("type") != VENDOR_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        return VendorContext(
            vendor_id=UUID(payload["vendor_id"]),
            vendor_contact_id=UUID(payload["vendor_contact_id"]),
            bid_invitation_id=UUID(payload["bid_invitation_id"]),
            bid_package_id=UUID(payload["bid_package_id"]),
            task_id=UUID(payload["task_id"]),
        )
    except (KeyError, ValueError) as e:
        logger.warning("Vendor JWT payload malformed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
