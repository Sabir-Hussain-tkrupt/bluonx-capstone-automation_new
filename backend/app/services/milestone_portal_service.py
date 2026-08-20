"""
Milestone check-in portal service (Phase 10.2).

Validates a milestone magic-link token and assembles the context the portal
needs to render the single Yes/No check-in question. Fully separate from the
bid flow: milestone tokens live in `milestone_checkin_tokens`, not
`magic_link_tokens`, and this is reached only by
POST /vendor-auth/validate-milestone-token.

Validation chain (order matters — each step short-circuits):
  1. SHA-256 hash → milestone_checkin_tokens lookup        → 404 if miss
  2. revoked_at set                                        → 410
  3. expires_at <= NOW()                                   → 410
  4. First-view is_used audit write (best-effort)
  5. Load milestone; token.cycle_number == milestones.cycle_number
                                                            → 410 if stale
  6. A milestone_responses row already exists for the alert → 200 already_answered
  7. milestones.status IN ('completed','cancelled')        → 410 (terminal)
  8. Actionable → issue milestone JWT + build context      → 200 actionable

Re-entry (is_used already TRUE) intentionally succeeds — the vendor re-clicks
after the JWT expires. "Spent" is enforced by the milestone_responses UNIQUE +
fn_record_milestone_response, never by is_used (audit-only), so a scanner
pre-fetch that hits validate can never record an answer.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from supabase import Client

from app.core.vendor_auth import VendorContext, issue_vendor_jwt
from app.models.vendor_portal import (
    MilestoneContextModel,
    MilestoneValidateResponse,
)

logger = logging.getLogger(__name__)

# milestone_alerts.alert_type → the portal check kind (drives the question).
_ALERT_TYPE_TO_CHECK: dict[str, str] = {
    "start_check": "start",
    "progress_check": "progress",
    "completion_check": "completion",
}

_TERMINAL_STATUSES = ("completed", "cancelled")


def _sha256(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _parse_expires_at(value: str) -> datetime:
    """Parse a Postgres timestamptz — may arrive with or without a tz offset."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def validate_milestone_token(
    db: Client, *, raw_token: str, client_ip: str
) -> MilestoneValidateResponse:
    """Validate a milestone check-in token → JWT + context, or a terminal outcome.

    Raises HTTPException (404/410) for invalid / expired / stale / terminal
    links; the router surfaces them as JSON the SPA routes on by status.
    """
    token_hash = _sha256(raw_token)

    # 1. Token exists?
    token_resp = (
        db.table("milestone_checkin_tokens")
        .select(
            "id, milestone_alert_id, milestone_id, vendor_contact_id,"
            " cycle_number, expires_at, is_used, revoked_at"
        )
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
    )
    token_rows = token_resp.data or []
    if not token_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or unknown check-in link",
        )
    token_row = token_rows[0]

    # 2. Revoked?
    if token_row.get("revoked_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This check-in link is no longer active",
        )

    # 3. Expired (7-day hard expiry)?
    if _parse_expires_at(token_row["expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This check-in link has expired",
        )

    # 4. First-view audit write (best-effort; re-clicks still validate).
    if not token_row["is_used"]:
        try:
            db.table("milestone_checkin_tokens").update(
                {
                    "is_used": True,
                    "used_at": datetime.now(timezone.utc).isoformat(),
                    "ip_address": client_ip,
                }
            ).eq("id", token_row["id"]).execute()
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to mark milestone token used: %s", e)

    # 5. Load milestone (identity, cycle, status) + task/project/vendor context.
    ms_resp = (
        db.table("milestones")
        .select(
            "id, name, end_date, status, cycle_number,"
            " tasks!inner(name, project_id, projects(name)),"
            " contracts!inner(vendor_id, vendors(company_name))"
        )
        .eq("id", token_row["milestone_id"])
        .maybe_single()
        .execute()
    )
    if not ms_resp or not ms_resp.data:
        # Orphaned token — milestone deleted after issuance. Treat as invalid.
        logger.warning(
            "Milestone token %s references missing milestone %s",
            token_row["id"],
            token_row["milestone_id"],
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or unknown check-in link",
        )
    ms = ms_resp.data

    # Cycle staleness: a reschedule bumped the cycle and stranded this link.
    if token_row["cycle_number"] != ms["cycle_number"]:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This check-in is no longer current",
        )

    # 6. Already answered? (immutable audit — one response per alert)
    answered_resp = (
        db.table("milestone_responses")
        .select("response_value, responded_at")
        .eq("milestone_alert_id", token_row["milestone_alert_id"])
        .limit(1)
        .execute()
    )
    answered_rows = answered_resp.data or []
    if answered_rows:
        answered = answered_rows[0]
        return MilestoneValidateResponse(
            outcome="already_answered",
            recorded_value=answered["response_value"],
            recorded_at=answered["responded_at"],
        )

    # 7. Terminal milestone? (a paused delayed/unresponsive one is still answerable)
    if ms["status"] in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This check-in is no longer current",
        )

    # 8. Resolve the check kind from the alert, then issue JWT + build context.
    alert_resp = (
        db.table("milestone_alerts")
        .select("alert_type")
        .eq("id", token_row["milestone_alert_id"])
        .maybe_single()
        .execute()
    )
    alert_type = ((alert_resp.data if alert_resp else None) or {}).get("alert_type")
    check_type = _ALERT_TYPE_TO_CHECK.get(alert_type or "")
    if check_type is None:
        # Not a vendor check-in alert — shouldn't happen for a minted token.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This check-in is no longer current",
        )

    task = ms.get("tasks") or {}
    project = task.get("projects") or {}
    contract = ms.get("contracts") or {}
    vendor = contract.get("vendors") or {}

    ctx = VendorContext(
        vendor_id=contract["vendor_id"],
        vendor_contact_id=token_row["vendor_contact_id"],
        milestone_alert_id=token_row["milestone_alert_id"],
        milestone_id=token_row["milestone_id"],
        cycle_number=token_row["cycle_number"],
    )
    milestone_context = MilestoneContextModel(
        milestone_alert_id=token_row["milestone_alert_id"],
        milestone_id=token_row["milestone_id"],
        milestone_name=ms.get("name") or "",
        project_name=project.get("name") or "",
        task_name=task.get("name") or "",
        vendor_company_name=vendor.get("company_name") or "",
        check_type=check_type,
        end_date=ms["end_date"],
        cycle_number=ms["cycle_number"],
    )
    return MilestoneValidateResponse(
        outcome="actionable",
        jwt=issue_vendor_jwt(ctx),
        milestone_context=milestone_context,
    )
