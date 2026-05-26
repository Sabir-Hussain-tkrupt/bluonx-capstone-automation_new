"""
Daily insurance-expiration monitoring job — notifies admins when vendors'
insurance certificates are approaching expiry (T-30 / T-7) or are past
their expiration date.

Reads vendors.insurance_expiration_date as the single source of truth.
Task 7.4.5 made that column a trustworthy mirror of the latest valid
insurance certificate (MAX(expiration_date) over vendor_documents where
status='valid'), so this job does not query vendor_documents at all.

Dedupe is done in-job via a pre-query against the notifications table so
the worker can accurately count `deduplicated_skipped`. NotificationService
itself also dedupes, but its return shape can't distinguish "inserted"
from "matched-existing-unread"; pre-checking lets us report partial-day
re-runs cleanly without modifying the service.

See backend/app/jobs/README.md for the job-authoring contract.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Callable

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

JOB_ID = "daily_insurance_expiration"

# Notification types this job emits — used to scope the dedupe pre-query.
_TYPES = ("insurance_expiring", "insurance_expired")


def _format_long_date(d: date) -> str:
    """Render a date as 'May 26, 2026' — matches the email digest format."""
    return d.strftime("%B %d, %Y")


def _resolve_tier(expiration: date, today: date) -> tuple[str, str] | None:
    """Map an expiration date to (notification_type, tier_counter_key), or
    None if the date isn't on a tier today.

    Tiers are exact-day matches (T-30, T-7) plus the open-ended past-today
    expired window — anything else inside the 30-day query window is
    intentionally skipped (it will hit a tier on a future day).
    """
    if expiration == today + timedelta(days=30):
        return ("insurance_expiring", "expiring_30day_notified")
    if expiration == today + timedelta(days=7):
        return ("insurance_expiring", "expiring_7day_notified")
    if expiration < today:
        return ("insurance_expired", "expired_notified")
    return None


def _build_payload(
    *, notification_type: str, vendor: dict, expiration: date, today: date
) -> tuple[str, str]:
    """Return (title, message) for a single notification."""
    company = vendor["company_name"]
    formatted = _format_long_date(expiration)

    if notification_type == "insurance_expired":
        days_ago = (today - expiration).days
        title = f"Insurance expired: {company}"
        message = (
            f"Insurance certificate for {company} expired on {formatted}. "
            f"Expired {days_ago} day(s) ago."
        )
        return title, message

    # insurance_expiring — derive 30/7 from the exact distance.
    days_until = (expiration - today).days
    title = f"Insurance expiring in {days_until} days: {company}"
    message = (
        f"Insurance certificate for {company} expires on {formatted}. "
        f"Expires in {days_until} days."
    )
    return title, message


def _list_active_admins(db) -> list[dict]:
    resp = (
        db.table("users")
        .select("id, email, full_name")
        .eq("role", "admin")
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .execute()
    )
    return resp.data or []


def _list_vendors_in_window(db, today: date) -> list[dict]:
    cutoff = today + timedelta(days=30)
    resp = (
        db.table("vendors")
        .select("id, company_name, insurance_expiration_date")
        .is_("deleted_at", "null")
        .not_.is_("insurance_expiration_date", "null")
        .lte("insurance_expiration_date", cutoff.isoformat())
        .execute()
    )
    return resp.data or []


def _existing_unread_triples(db) -> set[tuple[str, str, str]]:
    """Fetch the (user_id, notification_type, reference_id) triples that
    already have an unread row in `notifications` for any insurance type.
    The job uses this set to count dedupe hits and skip the redundant
    create_notification call.
    """
    triples: set[tuple[str, str, str]] = set()
    for ntype in _TYPES:
        resp = (
            db.table("notifications")
            .select("user_id, reference_id")
            .eq("notification_type", ntype)
            .eq("reference_type", "vendors")
            .eq("is_read", False)
            .execute()
        )
        for row in resp.data or []:
            ref = row.get("reference_id")
            user = row.get("user_id")
            if ref and user:
                triples.add((str(user), ntype, str(ref)))
    return triples


async def run_daily_insurance_expiration(
    db,
    notification_creator: Callable = create_notification,
) -> dict:
    """Daily worker body.

    `db` is a Supabase client; `notification_creator` is the callable used
    to insert notifications (defaults to NotificationService's module
    function). Tests inject mocks.
    """
    started = time.monotonic()
    today = date.today()

    counts = {
        "expiring_30day_notified": 0,
        "expiring_7day_notified": 0,
        "expired_notified": 0,
        "deduplicated_skipped": 0,
    }

    vendors = _list_vendors_in_window(db, today)
    if not vendors:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.info("insurance expiration: no vendors in window — %s", counts)
        return counts

    admins = _list_active_admins(db)
    if not admins:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.warning(
            "insurance expiration: vendors in window but no active admins to "
            "notify — %s",
            counts,
        )
        return counts

    existing = _existing_unread_triples(db)

    for vendor in vendors:
        raw = vendor.get("insurance_expiration_date")
        if not raw:
            continue
        try:
            expiration = date.fromisoformat(str(raw))
        except ValueError:
            logger.warning(
                "insurance expiration: unparseable date for vendor %s: %r",
                vendor.get("id"),
                raw,
            )
            continue

        tier = _resolve_tier(expiration, today)
        if tier is None:
            continue
        notification_type, counter_key = tier

        title, message = _build_payload(
            notification_type=notification_type,
            vendor=vendor,
            expiration=expiration,
            today=today,
        )
        vendor_id = str(vendor["id"])

        for admin in admins:
            admin_id = str(admin["id"])
            triple = (admin_id, notification_type, vendor_id)
            if triple in existing:
                counts["deduplicated_skipped"] += 1
                continue
            try:
                notification_creator(
                    db,
                    user_id=admin_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    reference_type="vendors",
                    reference_id=vendor_id,
                    dedupe=False,
                )
                counts[counter_key] += 1
                existing.add(triple)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "insurance expiration: failed to notify admin %s about "
                    "vendor %s: %s",
                    admin_id,
                    vendor_id,
                    exc,
                    exc_info=True,
                )

    counts["duration_seconds"] = round(time.monotonic() - started, 3)
    logger.info("insurance expiration complete: %s", counts)
    return counts


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    return await run_daily_insurance_expiration(db)


def register(scheduler) -> None:
    """Register the daily insurance-expiration monitoring job.

    Fires once a day at 15:15 UTC — ≈ 8:15 AM Mountain Time, a 15-minute
    offset from daily_bid_reminders so the two jobs don't contend.
    """
    scheduler.add_job(
        _run,
        CronTrigger(hour=15, minute=15),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 15:15 UTC)", JOB_ID)
