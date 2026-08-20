"""
Milestone check-in token minting (Phase 10.2 primitive).

Creates the vendor check-in `milestone_alerts` row AND its
`milestone_checkin_tokens` row together, and returns the portal URL the check-in
email links to. This is the outbound primitive: the Phase 10.3 daily send job
(out of scope here) will call `mint_checkin_token(...)` and pass the returned
`portal_url` straight into `milestone_email_service.send_milestone_check_email`.

The token is a bid-style magic link (raw emailed, SHA-256 hash stored) reusing
`_generate_magic_link_token`. It expires 7 days out (a hard cap independent of
cycle staleness) and is stamped with the milestone's current cycle_number, so a
later reschedule (which bumps the cycle) strands it declaratively.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from supabase import Client

from app.core.config import settings
from app.services.bid_package_service import _generate_magic_link_token
from app.services.milestone_service import MilestoneError

logger = logging.getLogger(__name__)

# alert_type values that are vendor check-ins (the only kinds a token is for).
_VENDOR_CHECK_ALERT_TYPES = ("start_check", "progress_check", "completion_check")

TOKEN_TTL_DAYS = 7


def _resolve_primary_contact_id(db: Client, milestone_id: str) -> str:
    """The vendor's primary contact id for this milestone's contract, or raise.

    milestone → contracts.vendor_id → vendor_contacts(is_primary). Raises
    MilestoneError(422) when the milestone, contract, or primary contact is
    missing so a mint never produces a token with a dangling FK.
    """
    ms_resp = (
        db.table("milestones")
        .select("id, contracts!inner(vendor_id)")
        .eq("id", milestone_id)
        .maybe_single()
        .execute()
    )
    if not ms_resp or not ms_resp.data:
        raise MilestoneError(422, "Milestone not found for check-in token")
    contract = ms_resp.data.get("contracts") or {}
    vendor_id = contract.get("vendor_id")
    if not vendor_id:
        raise MilestoneError(422, "Milestone has no contract vendor for check-in")

    contact_resp = (
        db.table("vendor_contacts")
        .select("id")
        .eq("vendor_id", str(vendor_id))
        .eq("is_primary", True)
        .limit(1)
        .execute()
    )
    rows = contact_resp.data or []
    if not rows:
        raise MilestoneError(
            422, "Vendor has no primary contact to send the check-in to"
        )
    return rows[0]["id"]


def mint_checkin_token(
    db: Client,
    *,
    milestone_id: UUID | str,
    alert_type: str,
    cycle_number: int,
) -> tuple[str, str]:
    """Create the vendor check-in alert + token; return (raw_token, portal_url).

    `alert_type` is a DB enum value (start_check / progress_check /
    completion_check). `cycle_number` must be the milestone's CURRENT cycle.
    """
    if alert_type not in _VENDOR_CHECK_ALERT_TYPES:
        raise MilestoneError(422, f"Not a vendor check-in alert type: {alert_type}")

    milestone_id = str(milestone_id)
    vendor_contact_id = _resolve_primary_contact_id(db, milestone_id)

    # 1. The alert row IS the check-in send record (dedup key for the job:
    #    milestone_id + alert_type + cycle_number). recipient_type='vendor'.
    alert_resp = (
        db.table("milestone_alerts")
        .insert(
            {
                "milestone_id": milestone_id,
                "alert_type": alert_type,
                "recipient_type": "vendor",
                "cycle_number": cycle_number,
            }
        )
        .execute()
    )
    alert_rows = alert_resp.data or []
    if not alert_rows:
        raise MilestoneError(500, "Failed to create milestone check-in alert")
    milestone_alert_id = alert_rows[0]["id"]

    # 2. Mint the token (raw emailed, hash stored). 7-day hard expiry.
    raw_token, token_hash = _generate_magic_link_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    db.table("milestone_checkin_tokens").insert(
        {
            "milestone_alert_id": milestone_alert_id,
            "milestone_id": milestone_id,
            "vendor_contact_id": vendor_contact_id,
            "cycle_number": cycle_number,
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
            "is_used": False,
            "revoked_at": None,
        }
    ).execute()

    portal_url = f"{settings.PORTAL_BASE_URL}/milestone/{raw_token}"
    return raw_token, portal_url
