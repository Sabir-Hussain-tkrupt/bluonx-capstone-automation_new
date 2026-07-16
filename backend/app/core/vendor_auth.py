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
    """Identity + scope derived from a validated vendor JWT.

    A context is exactly one KIND — bid XOR milestone — decided by which
    identity claims the token carries:
      - bid token:       vendor_id, vendor_contact_id, bid_invitation_id,
                         bid_package_id, task_id (+ optional bid_revision_request_id)
      - milestone token: vendor_id, vendor_contact_id, milestone_alert_id,
                         milestone_id, cycle_number

    `vendor_id` / `vendor_contact_id` are common to both. The bid fields are
    Optional so the same dataclass can hold a milestone identity, but the two
    dependencies below (`get_vendor_context` / `get_milestone_context`) assert
    the kind, so a bid endpoint never receives a milestone context and vice
    versa.
    """

    vendor_id: UUID
    vendor_contact_id: UUID
    # Bid identity (present only on bid tokens).
    bid_invitation_id: UUID | None = None
    bid_package_id: UUID | None = None
    task_id: UUID | None = None
    bid_revision_request_id: UUID | None = None
    # Milestone identity (present only on milestone tokens).
    milestone_alert_id: UUID | None = None
    milestone_id: UUID | None = None
    cycle_number: int | None = None

    @property
    def is_milestone(self) -> bool:
        return self.milestone_alert_id is not None

    @property
    def is_bid(self) -> bool:
        return self.bid_invitation_id is not None


def issue_vendor_jwt(ctx: VendorContext) -> str:
    """Sign a short-lived vendor JWT for the given context.

    Bid tokens carry the bid claims (byte-identical to before); milestone
    tokens carry ONLY the milestone claims and none of the bid ones — so an
    admin/bid token can never satisfy a milestone endpoint and vice versa.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "type": VENDOR_TOKEN_TYPE,
        "vendor_id": str(ctx.vendor_id),
        "vendor_contact_id": str(ctx.vendor_contact_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.VENDOR_JWT_EXPIRY_HOURS),
    }
    if ctx.is_milestone:
        payload["milestone_alert_id"] = str(ctx.milestone_alert_id)
        payload["milestone_id"] = str(ctx.milestone_id)
        payload["cycle_number"] = ctx.cycle_number
    else:
        payload["bid_invitation_id"] = str(ctx.bid_invitation_id)
        payload["bid_package_id"] = str(ctx.bid_package_id)
        payload["task_id"] = str(ctx.task_id)
        # Revision claim is OMITTED entirely for initial-bid tokens so existing
        # tokens stay bit-identical. Only revision tokens carry this claim.
        if ctx.bid_revision_request_id is not None:
            payload["bid_revision_request_id"] = str(ctx.bid_revision_request_id)
    return jwt.encode(payload, settings.VENDOR_JWT_SECRET, algorithm=VENDOR_JWT_ALGORITHM)


def _decode_vendor_jwt(token: str) -> dict:
    return jwt.decode(
        token,
        settings.VENDOR_JWT_SECRET,
        algorithms=[VENDOR_JWT_ALGORITHM],
    )


def _decode_and_validate(credentials: HTTPAuthorizationCredentials) -> dict:
    """Decode + verify the vendor JWT envelope (signature, expiry, type claim).

    Shared by both dependencies. Returns the raw payload; the identity-claim
    parsing is left to each dependency so they can enforce their kind.
    """
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
    return payload


async def get_vendor_context(
    credentials: HTTPAuthorizationCredentials = Depends(_vendor_bearer_scheme),
) -> VendorContext:
    """FastAPI dependency for BID endpoints: validate a bid vendor JWT.

    Rejects milestone tokens (a token carrying `milestone_alert_id` and no
    `bid_invitation_id`) so a milestone JWT can never satisfy a bid endpoint.
    Bid-token decoding is unchanged from before.
    """
    payload = _decode_and_validate(credentials)

    if payload.get("milestone_alert_id") is not None:
        # A milestone token must not be accepted by a bid endpoint.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        # Optional: absent for initial-bid tokens, present for revision tokens.
        # Read via .get() and never raise on absence.
        revision_raw = payload.get("bid_revision_request_id")
        bid_revision_request_id = UUID(revision_raw) if revision_raw else None
        return VendorContext(
            vendor_id=UUID(payload["vendor_id"]),
            vendor_contact_id=UUID(payload["vendor_contact_id"]),
            bid_invitation_id=UUID(payload["bid_invitation_id"]),
            bid_package_id=UUID(payload["bid_package_id"]),
            task_id=UUID(payload["task_id"]),
            bid_revision_request_id=bid_revision_request_id,
        )
    except (KeyError, ValueError) as e:
        logger.warning("Vendor JWT payload malformed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )


async def get_milestone_context(
    credentials: HTTPAuthorizationCredentials = Depends(_vendor_bearer_scheme),
) -> VendorContext:
    """FastAPI dependency for MILESTONE endpoints: validate a milestone vendor JWT.

    Rejects bid tokens (no `milestone_alert_id` claim) so a bid JWT can never
    satisfy a milestone endpoint. Vendor identity is read from the token only.
    """
    payload = _decode_and_validate(credentials)

    if payload.get("milestone_alert_id") is None:
        # A bid (or malformed) token must not be accepted by a milestone endpoint.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        return VendorContext(
            vendor_id=UUID(payload["vendor_id"]),
            vendor_contact_id=UUID(payload["vendor_contact_id"]),
            milestone_alert_id=UUID(payload["milestone_alert_id"]),
            milestone_id=UUID(payload["milestone_id"]),
            cycle_number=int(payload["cycle_number"]),
        )
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("Milestone vendor JWT payload malformed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
