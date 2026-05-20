"""
Per-vendor bid revision lifecycle service (Step 2 of the revision feature).

PM-facing operations (create / cancel / list) plus the vendor decline path.
The vendor's actual revised submission reuses the existing finalize endpoint
(Step 3) — not here.

All writes are single-statement supabase-py table ops. No db.rpc(), no
explicit transactions — the DB triggers + partial unique indexes are the
real integrity backstop; these checks are for friendly error messages.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from postgrest.exceptions import APIError

from app.core.config import settings
from app.models.bids import (
    BidRevisionRequestCreate,
    BidRevisionRequestCreateResponse,
    BidRevisionRequestResponse,
)
from app.services.bid_package_service import _generate_magic_link_token
from app.services.vendor_portal_service import _format_submitted_at

logger = logging.getLogger(__name__)

# Award statuses that block a new revision request for the task. Mirrors the
# partial unique index idx_awards_one_active_per_task (active = NOT IN
# declined_by_vendor/cancelled).
_BLOCKING_AWARD_STATUSES = ("pending_acceptance", "accepted")

# Lifetime cap per invitation. Counts every non-cancelled row (pending,
# submitted, declined, expired) — a cancelled request frees a slot.
_MAX_REVISIONS_PER_INVITATION = 2


class BidRevisionValidationError(Exception):
    """Raised on revision-request validation failure. Mirrors
    BidPackageValidationError — routers translate to HTTPException."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Helpers ──────────────────────────────────────────────────────────────


def _is_unique_violation(err: APIError) -> bool:
    """Heuristic — supabase-py wraps Postgres 23505 in APIError. Same logic
    as routers/vendor_portal.py:_is_unique_violation, replicated here to
    avoid a router→service import inversion."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23505" or "duplicate key" in msg or "unique" in msg


def _parse_timestamptz(value: str | datetime) -> datetime:
    """Parse a Postgres timestamptz — may arrive with or without a tz offset."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_response(row: dict) -> BidRevisionRequestResponse:
    return BidRevisionRequestResponse(**row)


# ── B.1 create ───────────────────────────────────────────────────────────


def create_revision_request(
    db,
    *,
    payload: BidRevisionRequestCreate,
    requested_by: UUID | str,
) -> BidRevisionRequestCreateResponse:
    """PM asks one vendor to revise their submitted bid."""
    invitation_id = str(payload.bid_invitation_id)

    # 1. Invitation exists.
    inv_resp = (
        db.table("bid_invitations")
        .select("id, vendor_id, bid_package_id")
        .eq("id", invitation_id)
        .limit(1)
        .execute()
    )
    inv_rows = inv_resp.data or []
    if not inv_rows:
        raise BidRevisionValidationError(404, "Bid invitation not found")
    invitation = inv_rows[0]

    # task_id (for the award guard) — via the parent bid package.
    pkg_resp = (
        db.table("bid_packages")
        .select("id, task_id")
        .eq("id", invitation["bid_package_id"])
        .limit(1)
        .execute()
    )
    pkg_rows = pkg_resp.data or []
    if not pkg_rows:
        raise BidRevisionValidationError(404, "Bid package not found")
    task_id = pkg_rows[0]["task_id"]

    # 2. A current (non-superseded, finalized) submission must exist. Its id
    #    is the original being revised — server-derived, never client-supplied.
    sub_resp = (
        db.table("bid_submissions")
        .select("id")
        .eq("bid_invitation_id", invitation_id)
        .eq("is_superseded", False)
        .eq("is_draft", False)
        .limit(1)
        .execute()
    )
    sub_rows = sub_resp.data or []
    if not sub_rows:
        raise BidRevisionValidationError(
            422, "No submitted bid exists for this invitation to revise"
        )
    original_submission_id = sub_rows[0]["id"]

    # 3. No blocking award on the task.
    award_resp = (
        db.table("awards")
        .select("id, status")
        .eq("task_id", task_id)
        .in_("status", list(_BLOCKING_AWARD_STATUSES))
        .limit(1)
        .execute()
    )
    if award_resp.data:
        raise BidRevisionValidationError(
            409, "Cannot request a revision after the task has been awarded"
        )

    # 4. Lifetime cap — count non-cancelled requests for this invitation.
    existing_resp = (
        db.table("bid_revision_requests")
        .select("id, status")
        .eq("bid_invitation_id", invitation_id)
        .neq("status", "cancelled")
        .execute()
    )
    if len(existing_resp.data or []) >= _MAX_REVISIONS_PER_INVITATION:
        raise BidRevisionValidationError(
            409,
            f"Revision limit reached ({_MAX_REVISIONS_PER_INVITATION} per vendor)",
        )

    # 5. Deadline must be in the future.
    if _parse_timestamptz(payload.revision_deadline) <= datetime.now(timezone.utc):
        raise BidRevisionValidationError(
            422, "revision_deadline must be in the future"
        )

    # 6. Insert the request. The partial unique index
    #    idx_bid_revision_requests_one_pending_per_invitation enforces the
    #    one-pending invariant atomically — surface its violation as 409.
    insert_row = {
        "bid_invitation_id": invitation_id,
        "original_submission_id": original_submission_id,
        "pm_note": payload.pm_note,
        "revision_deadline": _parse_timestamptz(
            payload.revision_deadline
        ).isoformat(),
        "requested_by": str(requested_by),
    }
    try:
        created_resp = (
            db.table("bid_revision_requests").insert(insert_row).execute()
        )
    except APIError as e:
        if _is_unique_violation(e):
            raise BidRevisionValidationError(
                409,
                "A pending revision request already exists for this invitation",
            ) from e
        raise
    created = (created_resp.data or [None])[0]
    if not created:
        raise BidRevisionValidationError(500, "Failed to create revision request")

    # 7. Issue the magic-link token (expires with the per-request deadline).
    raw_token, token_hash = _generate_magic_link_token()
    db.table("magic_link_tokens").insert(
        {
            "bid_invitation_id": invitation_id,
            "vendor_id": invitation["vendor_id"],
            "token_hash": token_hash,
            "expires_at": insert_row["revision_deadline"],
            "is_used": False,
            "revoked_at": None,
            "bid_revision_request_id": created["id"],
        }
    ).execute()

    portal_url = f"{settings.PORTAL_BASE_URL}/bid/{raw_token}"
    return BidRevisionRequestCreateResponse(
        revision_request=_to_response(created),
        magic_link_token=raw_token,
        portal_url=portal_url,
    )


# ── B.2 cancel ───────────────────────────────────────────────────────────


def cancel_revision_request(
    db,
    *,
    revision_request_id: UUID | str,
    cancelled_by: UUID | str,
) -> BidRevisionRequestResponse:
    """PM cancels a still-pending revision request."""
    rid = str(revision_request_id)

    existing = (
        db.table("bid_revision_requests")
        .select("id, status")
        .eq("id", rid)
        .limit(1)
        .execute()
    )
    rows = existing.data or []
    if not rows:
        raise BidRevisionValidationError(404, "Revision request not found")
    if rows[0]["status"] != "pending":
        raise BidRevisionValidationError(
            409, "Only a pending revision request can be cancelled"
        )

    # Guarded write. The .eq("status","pending") makes this a no-op if a
    # concurrent decline/finalize/cancel already moved it off pending; an
    # empty result set means we lost that race → 409 (TOCTOU guard).
    updated = (
        db.table("bid_revision_requests")
        .update({"status": "cancelled"})
        .eq("id", rid)
        .eq("status", "pending")
        .execute()
    )
    updated_rows = updated.data or []
    if not updated_rows:
        raise BidRevisionValidationError(
            409, "Revision request is no longer pending"
        )

    # Revoke the associated magic link(s). The WHERE clause is plural-safe:
    # the current design issues exactly one token per revision request, but
    # this revokes all matching rows if that ever changes.
    db.table("magic_link_tokens").update(
        {
            "is_used": True,
            "revoked_at": _now_iso(),
            "revoked_by": str(cancelled_by),
        }
    ).eq("bid_revision_request_id", rid).execute()

    return _to_response(updated_rows[0])


# ── B.3 list ─────────────────────────────────────────────────────────────


def list_revision_requests_for_package(
    db,
    *,
    bid_package_id: UUID | str,
) -> list[BidRevisionRequestResponse]:
    """All revision requests for a bid package, newest first.

    bid_revision_requests has no bid_package_id — resolve via the package's
    invitations.
    """
    inv_resp = (
        db.table("bid_invitations")
        .select("id")
        .eq("bid_package_id", str(bid_package_id))
        .execute()
    )
    invitation_ids = [r["id"] for r in (inv_resp.data or [])]
    if not invitation_ids:
        return []

    rr_resp = (
        db.table("bid_revision_requests")
        .select(
            "id, bid_invitation_id, original_submission_id, pm_note,"
            " revision_deadline, status, decline_reason, requested_by,"
            " requested_at, responded_at, created_at, updated_at"
        )
        .in_("bid_invitation_id", invitation_ids)
        .order("requested_at", desc=True)
        .execute()
    )
    return [_to_response(r) for r in (rr_resp.data or [])]


# ── B.5 vendor decline (SPA-mediated, vendor JWT) ────────────────────────


def decline_revision_request(
    db,
    *,
    revision_request_id: UUID | str,
    decline_reason: str | None,
) -> BidRevisionRequestResponse:
    """Vendor declines a pending revision request from the SPA.

    Auth + JWT-claim/path-id binding are enforced by the router (the vendor
    JWT is the credential). This function owns the state transition only.
    Raises HTTPException — the JWT router surfaces it as JSON.
    """
    rid = str(revision_request_id)

    existing = (
        db.table("bid_revision_requests")
        .select("id")
        .eq("id", rid)
        .limit(1)
        .execute()
    )
    if not (existing.data or []):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revision request not found",
        )

    # Guarded write. The .eq("status","pending") makes this a no-op if the
    # request already moved off pending (terminal state or concurrent
    # decline/finalize/cancel) — empty result ⇒ 410 (covers both cases).
    updated = (
        db.table("bid_revision_requests")
        .update(
            {
                "status": "declined",
                "decline_reason": decline_reason,
                "responded_at": _now_iso(),
            }
        )
        .eq("id", rid)
        .eq("status", "pending")
        .execute()
    )
    if not (updated.data or []):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This revision request is no longer active",
        )

    # Revoke the token(s). revoked_by stays NULL — a vendor action has no
    # users row. The column is nullable. Plural-safe WHERE (see B.2).
    db.table("magic_link_tokens").update(
        {"is_used": True, "revoked_at": _now_iso()}
    ).eq("bid_revision_request_id", rid).execute()

    # Re-read the full row so the response matches the PM endpoints' shape.
    refreshed = (
        db.table("bid_revision_requests")
        .select(
            "id, bid_invitation_id, original_submission_id, pm_note,"
            " revision_deadline, status, decline_reason, requested_by,"
            " requested_at, responded_at, created_at, updated_at"
        )
        .eq("id", rid)
        .limit(1)
        .execute()
    )
    return _to_response((refreshed.data or [updated.data[0]])[0])


# ── F.1 revision-request email (best-effort, mirrors ──────────────────────
# vendor_portal_service.send_submission_confirmation_email) ────────────────


async def send_revision_request_email(
    *,
    email_service: Any,
    template_renderer: Any,
    db,
    bid_invitation_id: UUID | str,
    revision_request_id: UUID | str,
    pm_note: str,
    revision_deadline: datetime,
    portal_url: str,
) -> bool:
    """Render and send the revision-request email. Best-effort.

    Returns True iff the provider reported 'sent'. Never raises — the
    revision request is already committed; a failed send is an ops issue
    (retry from the email_log), not a PM-facing failure.
    """
    # One joined read for the vendor/project/task fields — mirrors the
    # select shape of vendor_portal._fetch_submission_email_context.
    try:
        resp = (
            db.table("bid_invitations")
            .select(
                "id,"
                " vendor_contacts(full_name, email),"
                " vendors(company_name),"
                " bid_packages!inner("
                "   tasks!inner("
                "     name,"
                "     projects(name)"
                "   )"
                " )"
            )
            .eq("id", str(bid_invitation_id))
            .single()
            .execute()
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to fetch email context for revision request %s",
            revision_request_id,
        )
        return False

    inv = resp.data or {}
    contact = inv.get("vendor_contacts") or {}
    vendor = inv.get("vendors") or {}
    pkg = inv.get("bid_packages") or {}
    task = pkg.get("tasks") or {}
    project = task.get("projects") or {}

    to_email = (contact.get("email") or "").strip()
    if not to_email:
        logger.warning(
            "Revision request %s has no vendor contact email; skipping send",
            revision_request_id,
        )
        return False

    render_ctx = {
        "vendor_contact_name": contact.get("full_name") or "",
        "vendor_company_name": vendor.get("company_name") or "",
        "project_name": project.get("name") or "",
        "task_name": task.get("name") or "",
        "pm_note": pm_note,
        "revision_deadline_formatted": _format_submitted_at(revision_deadline),
        "portal_url": portal_url,
    }

    try:
        html_body = template_renderer.render(
            "bid_revision_request.html", render_ctx
        )
        text_body = template_renderer.render_text(
            "bid_revision_request.txt", render_ctx
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to render revision-request email for %s",
            revision_request_id,
        )
        return False

    subject = (
        f"Revision Requested: {render_ctx['project_name']}"
        f" — {render_ctx['task_name']}"
    )
    try:
        result = await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=text_body,
            email_type="general",
            recipient_type="vendor_contact",
            reference_type="bid_revision_requests",
            reference_id=str(revision_request_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Revision-request email send raised for %s", revision_request_id
        )
        return False

    return getattr(result, "status", None) == "sent"
