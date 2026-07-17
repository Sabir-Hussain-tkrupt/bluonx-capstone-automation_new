"""
Daily scheduler self-check job (Task 7.8).

Inspects the in-memory ``_last_run`` state of every tracked job (except the
self-check itself) and notifies active admins via in-app notification
(``notification_type='scheduler_alert'``) when any job is stale beyond its
expected interval plus a 2-hour grace window.

Per the Phase 7 channel-split rule, admin alerts are notifications only — no
email. Dedupe matches Tasks 7.5/7.6: in-job pre-query of unread
``scheduler_alert`` notifications, then per-recipient fan-out with
``dedupe=False`` so the worker's own counters stay accurate. A persistent
staleness condition therefore yields one alert per admin until they read it,
not one per day.

The self-check excludes itself from evaluation — it cannot usefully
self-evaluate, and that blind spot is intentional (Sentry + ECS health
checks cover the "whole scheduler down" case).
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import (
    DEFAULT_JOB_KWARGS,
    get_last_run,
    get_scheduler_started_at,
    tracked_job,
)
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

JOB_ID = "scheduler_self_check"
_NOTIFICATION_TYPE = "scheduler_alert"

# Jobs the self-check evaluates. scheduler_self_check is intentionally absent.
EXPECTED_INTERVALS: dict[str, timedelta] = {
    "revision_expiry": timedelta(hours=1),
    "daily_bid_reminders": timedelta(days=1),
    "daily_insurance_expiration": timedelta(days=1),
    "post_deadline_escalation": timedelta(days=1),
    "milestone_daily_checkin": timedelta(days=1),
    "milestone_no_response": timedelta(days=1),
}
GRACE_WINDOW = timedelta(hours=2)


def _format_interval(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total and total % 86400 == 0:
        d = total // 86400
        return f"{d} day" if d == 1 else f"{d} days"
    if total and total % 3600 == 0:
        h = total // 3600
        return f"{h} hour" if h == 1 else f"{h} hours"
    return str(td)


def _parse_last_run_at(payload: dict | None) -> datetime | None:
    if not payload or not payload.get("last_run_at"):
        return None
    return datetime.fromisoformat(payload["last_run_at"])


def _detect_stale_jobs(now: datetime) -> list[dict]:
    """Return [{job_id, interval_str, last_run_str}, ...] for stale jobs."""
    started_at = get_scheduler_started_at()
    stale: list[dict] = []
    for job_id, interval in EXPECTED_INTERVALS.items():
        threshold = interval + GRACE_WINDOW
        last_run_at = _parse_last_run_at(get_last_run(job_id))
        if last_run_at is None:
            if started_at is not None and (now - started_at) < threshold:
                continue
            stale.append(
                {
                    "job_id": job_id,
                    "interval_str": _format_interval(interval),
                    "last_run_str": "never",
                }
            )
            continue
        if last_run_at < now - threshold:
            stale.append(
                {
                    "job_id": job_id,
                    "interval_str": _format_interval(interval),
                    "last_run_str": last_run_at.isoformat(),
                }
            )
    return stale


def _build_message(stale: list[dict]) -> str:
    lines = [
        f"{s['job_id']}: expected every {s['interval_str']}, last ran {s['last_run_str']}"
        for s in stale
    ]
    lines.append("Check /api/v1/admin/scheduler-health for current state.")
    return "\n".join(lines)


def _fetch_active_admins(db) -> list[dict]:
    result = (
        db.table("users")
        .select("id")
        .eq("role", "admin")
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .execute()
    )
    return result.data or []


def _existing_unread_admin_ids(db, admin_ids: list[str]) -> set[str]:
    if not admin_ids:
        return set()
    result = (
        db.table("notifications")
        .select("user_id")
        .eq("notification_type", _NOTIFICATION_TYPE)
        .eq("is_read", False)
        .in_("user_id", admin_ids)
        .execute()
    )
    return {row["user_id"] for row in (result.data or [])}


async def run_daily_scheduler_self_check(
    db,
    notification_creator: Callable = create_notification,
) -> dict:
    started = time.monotonic()
    now = datetime.now(timezone.utc)

    stale = _detect_stale_jobs(now)
    counts: dict = {
        "stale_jobs": [s["job_id"] for s in stale],
        "admins_notified": 0,
        "deduplicated_skipped": 0,
        "duration_seconds": 0.0,
    }

    if not stale:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.info("scheduler_self_check: no stale jobs")
        return counts

    admins = _fetch_active_admins(db)
    if not admins:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.warning(
            "scheduler_self_check: %d stale job(s) detected but no active admins to notify",
            len(stale),
        )
        return counts

    admin_ids = [str(a["id"]) for a in admins]
    skip_set = _existing_unread_admin_ids(db, admin_ids)

    n = len(stale)
    title = "Scheduler alert: 1 job stale" if n == 1 else f"Scheduler alert: {n} jobs stale"
    message = _build_message(stale)

    for admin_id in admin_ids:
        if admin_id in skip_set:
            counts["deduplicated_skipped"] += 1
            continue
        try:
            notification_creator(
                db,
                user_id=admin_id,
                notification_type=_NOTIFICATION_TYPE,
                title=title,
                message=message,
                reference_type=None,
                reference_id=None,
                dedupe=False,
            )
            counts["admins_notified"] += 1
        except Exception as exc:  # noqa: BLE001 — per-recipient isolation
            logger.error(
                "scheduler_self_check: failed to notify admin %s: %s",
                admin_id,
                exc,
                exc_info=True,
            )

    counts["duration_seconds"] = round(time.monotonic() - started, 3)
    logger.info(
        "scheduler_self_check complete: %d stale, %d notified, %d deduped",
        n,
        counts["admins_notified"],
        counts["deduplicated_skipped"],
    )
    return counts


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    return await run_daily_scheduler_self_check(db)


def register(scheduler) -> None:
    """Register the daily scheduler self-check job.

    Fires once a day at 15:45 UTC — ≈ 8:45 AM Mountain Time, runs 30 min after
    daily_bid_reminders so primary jobs have had a chance to record their runs.
    """
    scheduler.add_job(
        _run,
        CronTrigger(hour=15, minute=45),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 15:45 UTC)", JOB_ID)
