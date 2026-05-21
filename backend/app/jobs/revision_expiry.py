"""
Revision-expiry job — auto-transitions overdue bid revision requests.

When a vendor neither submits nor declines a per-vendor bid revision by its
deadline, the request stays 'pending' forever — nothing else transitions it.
This hourly job finds those overdue requests, marks them 'expired', and
revokes their magic-link tokens. The token revocation mirrors the PM cancel
flow in bid_revision_service.cancel_revision_request.
"""

import logging
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job

logger = logging.getLogger(__name__)

JOB_ID = "revision_expiry"


async def expire_revision_requests(db) -> int:
    """Find pending revision requests past their deadline and mark them expired."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # Find pending requests past their deadline.
    resp = (
        db.table("bid_revision_requests")
        .select("id, bid_invitation_id")
        .eq("status", "pending")
        .lt("revision_deadline", now_iso)
        .execute()
    )
    expired_rows = resp.data or []

    expired_count = 0
    for row in expired_rows:
        # TOCTOU-safe: the .eq("status", "pending") guard makes this UPDATE a
        # no-op if a vendor response or PM cancel moved the row off 'pending'
        # between the SELECT above and now. Mirrors cancel_revision_request.
        update_resp = (
            db.table("bid_revision_requests")
            .update({"status": "expired", "responded_at": now_iso})
            .eq("id", row["id"])
            .eq("status", "pending")
            .execute()
        )
        if not update_resp.data:
            continue  # Lost the race — vendor responded or PM cancelled.

        # Revoke the magic-link token(s) for this request. No revoked_by is
        # set: no user took this action (the column is nullable). Mirrors the
        # vendor-decline path in bid_revision_service.
        (
            db.table("magic_link_tokens")
            .update({"revoked_at": now_iso, "is_used": True})
            .eq("bid_revision_request_id", row["id"])
            .execute()
        )

        expired_count += 1

    return expired_count


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    count = await expire_revision_requests(db)
    return {"expired_count": count}


def register(scheduler) -> None:
    """Register the revision-expiry job. Runs hourly at :00 UTC."""
    scheduler.add_job(
        _run,
        CronTrigger(minute=0),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (hourly at :00 UTC)", JOB_ID)
