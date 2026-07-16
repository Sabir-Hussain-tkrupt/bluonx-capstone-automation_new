"""
Vendor portal authentication endpoints (Phase 5).

Public endpoint — NO admin auth. Validates a magic-link token, issues a
short-lived vendor JWT, and returns the full bid context needed to render
the multi-step bid submission form in one call.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from supabase import Client

from app.core.rate_limit import validate_token_rate_limit
from app.core.supabase_client import get_supabase
from app.core.vendor_auth import VendorContext, issue_vendor_jwt
from app.models.vendor_portal import (
    MilestoneValidateResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from app.services.milestone_portal_service import validate_milestone_token
from app.services.vendor_portal_service import build_bid_context

logger = logging.getLogger(__name__)

router = APIRouter()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _parse_expires_at(value: str) -> datetime:
    """Parse a Postgres timestamptz — may arrive with or without a tz offset."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.post(
    "/vendor-auth/validate-token",
    response_model=ValidateTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def validate_magic_link_token(
    payload: ValidateTokenRequest,
    request: Request,
    _rl: None = Depends(validate_token_rate_limit),
    db: Client = Depends(get_supabase),
) -> ValidateTokenResponse:
    """Exchange a raw magic-link token for a vendor JWT + bid context.

    Validation chain (order matters — each step short-circuits):
      1. SHA-256 hash → magic_link_tokens lookup   → 404 if miss
      2. expires_at > NOW()                          → 410 if past
      3. bid_packages.status == 'open'              → 423 if closed/cancelled
      4. No non-draft bid_submission for invitation → 409 if already submitted
      5. Mark token used on first click (is_used = TRUE, used_at, ip_address)
      6. Issue vendor JWT + assemble bid_context

    Re-entry (is_used already TRUE) intentionally succeeds — vendors re-click
    the magic link after JWT expiry to resume from draft. The token remains
    valid for the life of the bid deadline.
    """
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

    # 1. Token exists?
    token_resp = (
        db.table("magic_link_tokens")
        .select(
            "id, bid_invitation_id, expires_at, is_used, revoked_at,"
            " bid_revision_request_id"
        )
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
    )
    token_rows = token_resp.data or []
    if not token_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or unknown bid link",
        )
    token_row = token_rows[0]

    # 2a. Token revoked? Resend Bid Link hard-revokes all prior tokens.
    # Runs before the is_used audit-write so a revoked token is never
    # treated as resumable, regardless of its is_used state.
    if token_row.get("revoked_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "This bid link has been revoked. "
                "Please use the most recent link sent to your email."
            ),
        )

    # 2b. Token still valid?
    if _parse_expires_at(token_row["expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This bid link has expired",
        )

    # Discriminator: NULL = initial-bid token, non-NULL = revision token.
    # Revision tokens bypass the package-status and "already submitted" gates
    # and instead require their revision request to still be pending.
    is_revision_token = token_row.get("bid_revision_request_id") is not None

    # 3. Bid package still open? Also pulls the invitation + package identity
    #    we need for the JWT and the 409 check.
    invitation_resp = (
        db.table("bid_invitations")
        .select(
            "id, vendor_id, vendor_contact_id, bid_package_id, status, opened_at,"
            " bid_packages(id, status, task_id)"
        )
        .eq("id", token_row["bid_invitation_id"])
        .single()
        .execute()
    )
    if not invitation_resp.data:
        # Orphaned token — invitation was deleted after issuance. Treat as
        # invalid, not expired, so the user lands on the right error page.
        logger.warning(
            "Magic link token %s references missing invitation %s",
            token_row["id"],
            token_row["bid_invitation_id"],
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or unknown bid link",
        )

    invitation = invitation_resp.data
    pkg = invitation["bid_packages"]

    if is_revision_token:
        # Revision tokens deliberately skip gate 3 (package status) and gate 4
        # (no non-draft submission) — a revision exists precisely because a
        # finalized submission is present, and the revision deadline is
        # independent of the package deadline. The pending-request check below
        # is the gate for revision tokens.
        revision_resp = (
            db.table("bid_revision_requests")
            .select("id, status")
            .eq("id", token_row["bid_revision_request_id"])
            .limit(1)
            .execute()
        )
        revision_rows = revision_resp.data or []
        if not revision_rows or revision_rows[0]["status"] != "pending":
            # Covers submitted/declined/expired/cancelled terminal states and
            # the (shouldn't-happen) deleted-request case.
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This revision request is no longer active",
            )
    else:
        # 3. Bid package still open?
        if pkg["status"] != "open":
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Bidding for this package is closed",
            )

        # 4. Already submitted (non-draft)?
        existing_resp = (
            db.table("bid_submissions")
            .select("id, is_draft")
            .eq("bid_invitation_id", invitation["id"])
            .limit(1)
            .execute()
        )
        existing_rows = existing_resp.data or []
        if existing_rows and existing_rows[0]["is_draft"] is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A bid has already been submitted for this invitation",
            )

    # 5. First use only — mark token consumed + capture IP.
    if not token_row["is_used"]:
        try:
            db.table("magic_link_tokens").update(
                {
                    "is_used": True,
                    "used_at": datetime.now(timezone.utc).isoformat(),
                    "ip_address": _client_ip(request),
                }
            ).eq("id", token_row["id"]).execute()
        except Exception as e:
            # Non-fatal: a failed audit-write should not block the vendor
            # from entering the portal. Log and continue.
            logger.warning("Failed to mark magic link token used: %s", e)

    # 6. Advance invitation 'sent' → 'opened' on first view. Idempotent —
    #    re-entries (status already opened/submitted/etc.) leave the row
    #    untouched so opened_at preserves the original first-view timestamp.
    if invitation.get("status") == "sent":
        update_payload = {"status": "opened"}
        if invitation.get("opened_at") is None:
            update_payload["opened_at"] = datetime.now(timezone.utc).isoformat()
        try:
            db.table("bid_invitations").update(update_payload).eq(
                "id", invitation["id"]
            ).execute()
        except Exception as e:
            # Non-fatal: failing to stamp the open should not block entry.
            logger.warning("Failed to mark invitation opened: %s", e)

    # 7. Issue JWT + assemble context.
    ctx = VendorContext(
        vendor_id=invitation["vendor_id"],
        vendor_contact_id=invitation["vendor_contact_id"],
        bid_invitation_id=invitation["id"],
        bid_package_id=pkg["id"],
        task_id=pkg["task_id"],
        bid_revision_request_id=token_row.get("bid_revision_request_id"),
    )
    jwt_token = issue_vendor_jwt(ctx)
    bid_context = build_bid_context(
        db, ctx.bid_invitation_id, ctx.bid_revision_request_id
    )

    return ValidateTokenResponse(jwt=jwt_token, bid_context=bid_context)


@router.post(
    "/vendor-auth/validate-milestone-token",
    response_model=MilestoneValidateResponse,
    status_code=status.HTTP_200_OK,
)
async def validate_milestone_magic_link_token(
    payload: ValidateTokenRequest,
    request: Request,
    _rl: None = Depends(validate_token_rate_limit),
    db: Client = Depends(get_supabase),
) -> MilestoneValidateResponse:
    """Exchange a raw milestone check-in token for a vendor JWT + context.

    Fully separate from the bid validate path above — milestone tokens live in
    their own table. Returns one of:
      - actionable       → jwt + milestone_context (render the Yes/No page)
      - already_answered → recorded value + date (no jwt; render the recorded page)
    or raises 404 (unknown) / 410 (revoked / expired / stale / terminal), which
    the SPA routes to the invalid / no-longer-current pages.
    """
    return validate_milestone_token(
        db, raw_token=payload.token, client_ip=_client_ip(request)
    )
