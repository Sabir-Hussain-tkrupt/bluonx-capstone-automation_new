"""
Post-deadline admin escalation job (Task 7.6).

Notifies each bid-package creator (the PM) the morning after their packages
closed with non-responding vendors, then transitions those invitations from
'sent'/'opened' to 'no_response' so the dashboard reflects the now-
acknowledged escalation state.

Mirrors the structural pattern of the sibling Task 7.5 insurance-expiration
job:
  - testable worker `run_daily_post_deadline_escalation(db, notification_creator=...)`
  - thin @tracked_job-decorated `_run()` as the scheduler entrypoint
  - in-job dedupe pre-query against the `notifications` table so
    `deduplicated_skipped` is counted accurately; `create_notification`
    is invoked with dedupe=False

See backend/app/jobs/README.md for the job-authoring contract.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

JOB_ID = "post_deadline_escalation"
_NOTIFICATION_TYPE = "post_deadline_non_responders"
_NON_RESPONDING_STATUSES = ("sent", "opened")


def _candidate_packages(db, now_iso: str, cutoff_iso: str) -> list[dict]:
    """Bid packages whose deadline fell within the last 24 hours.

    Pulls task + project names via PostgREST embedded select so the
    notification title can be built without per-package lookups.
    """
    resp = (
        db.table("bid_packages")
        .select(
            "id, deadline, created_by, "
            "tasks(name, project_id, projects(name))"
        )
        .lt("deadline", now_iso)
        .gte("deadline", cutoff_iso)
        .execute()
    )
    return resp.data or []


def _non_responders(db, package_id: str) -> list[dict]:
    """Invitations for one package whose status indicates no response."""
    resp = (
        db.table("bid_invitations")
        .select(
            "id, vendor_id, vendor_contact_id, status, "
            "vendors(company_name), "
            "vendor_contacts(full_name, email)"
        )
        .eq("bid_package_id", package_id)
        .in_("status", list(_NON_RESPONDING_STATUSES))
        .execute()
    )
    return resp.data or []


def _get_active_creator(db, user_id: str, cache: dict) -> dict | None:
    """Fetch (and cache) an active, non-deleted user row, or None.

    Caches the resolution per run so a creator who owns multiple affected
    packages only triggers one users-table query.
    """
    if user_id in cache:
        return cache[user_id]
    resp = (
        db.table("users")
        .select("id, email, full_name, is_active, deleted_at")
        .eq("id", user_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .execute()
    )
    user = (resp.data or [None])[0]
    cache[user_id] = user
    return user


def _existing_unread_pairs(db, package_ids: list[str]) -> set[tuple[str, str]]:
    """Set of (user_id, bid_package_id) that already have an unread
    post_deadline_non_responders notification for one of the affected
    packages. Used to skip same-day re-runs."""
    if not package_ids:
        return set()
    resp = (
        db.table("notifications")
        .select("user_id, reference_id")
        .eq("notification_type", _NOTIFICATION_TYPE)
        .eq("reference_type", "bid_packages")
        .eq("is_read", False)
        .in_("reference_id", package_ids)
        .execute()
    )
    pairs: set[tuple[str, str]] = set()
    for row in resp.data or []:
        user_id = row.get("user_id")
        ref_id = row.get("reference_id")
        if user_id and ref_id:
            pairs.add((str(user_id), str(ref_id)))
    return pairs


def _build_payload(
    *, project_name: str, task_name: str, non_responders: list[dict]
) -> tuple[str, str]:
    """Render the (title, message) pair for one affected package."""
    n = len(non_responders)
    title = f"{n} vendors did not respond: {project_name} / {task_name}"

    lines: list[str] = []
    for inv in non_responders[:5]:
        company = (inv.get("vendors") or {}).get("company_name") or "(unknown vendor)"
        contact = inv.get("vendor_contacts") or {}
        contact_name = contact.get("full_name") or "(unknown contact)"
        contact_email = contact.get("email") or "(no email)"
        lines.append(f"{company} — {contact_name} ({contact_email})")
    if n > 5:
        lines.append(f"...and {n - 5} more.")
    return title, "\n".join(lines)


async def run_daily_post_deadline_escalation(
    db,
    notification_creator: Callable = create_notification,
) -> dict:
    """Daily worker body — see module docstring.

    `db` is a Supabase client; `notification_creator` is the callable used
    to insert notifications (defaults to NotificationService). Tests inject
    mocks to observe calls and induce failure.
    """
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    counts = {
        "packages_affected": 0,
        "notifications_created": 0,
        "invitations_marked_no_response": 0,
        "deduplicated_skipped": 0,
        "skipped_inactive_creator": 0,
    }

    candidates = _candidate_packages(db, now.isoformat(), cutoff.isoformat())
    if not candidates:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.info("post-deadline escalation: no packages in window — %s", counts)
        return counts

    # Filter candidates to packages that actually have at least one non-responder.
    affected: list[tuple[dict, list[dict]]] = []
    for pkg in candidates:
        nrs = _non_responders(db, str(pkg["id"]))
        if nrs:
            affected.append((pkg, nrs))

    counts["packages_affected"] = len(affected)
    if not affected:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.info("post-deadline escalation: no affected packages — %s", counts)
        return counts

    # Dedupe pre-query, scoped to the affected package ids.
    affected_ids = [str(pkg["id"]) for pkg, _ in affected]
    existing = _existing_unread_pairs(db, affected_ids)

    user_cache: dict[str, dict | None] = {}

    for pkg, non_responders in affected:
        pkg_id = str(pkg["id"])
        creator_id_raw = pkg.get("created_by")
        if not creator_id_raw:
            logger.warning(
                "post-deadline escalation: package %s has no created_by; skipping",
                pkg_id,
            )
            continue
        creator_id = str(creator_id_raw)

        creator = _get_active_creator(db, creator_id, user_cache)
        if creator is None:
            counts["skipped_inactive_creator"] += 1
            continue

        if (creator_id, pkg_id) in existing:
            counts["deduplicated_skipped"] += 1
            continue

        task = pkg.get("tasks") or {}
        project = task.get("projects") or {}
        title, message = _build_payload(
            project_name=project.get("name") or "(unknown project)",
            task_name=task.get("name") or "(unknown task)",
            non_responders=non_responders,
        )

        notified = False
        try:
            notification_creator(
                db,
                user_id=creator_id,
                notification_type=_NOTIFICATION_TYPE,
                title=title,
                message=message,
                reference_type="bid_packages",
                reference_id=pkg_id,
                dedupe=False,
            )
            counts["notifications_created"] += 1
            notified = True
        except Exception as exc:  # noqa: BLE001 — never crash the scheduler
            logger.error(
                "post-deadline escalation: failed to notify creator %s about "
                "package %s: %s",
                creator_id,
                pkg_id,
                exc,
                exc_info=True,
            )

        if not notified:
            # Notification dispatch failed for the only recipient — do NOT
            # flip invitations. The escalation didn't actually happen.
            continue

        try:
            resp = (
                db.table("bid_invitations")
                .update({"status": "no_response"})
                .eq("bid_package_id", pkg_id)
                .in_("status", list(_NON_RESPONDING_STATUSES))
                .execute()
            )
            counts["invitations_marked_no_response"] += len(resp.data or [])
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "post-deadline escalation: failed to flip invitations for "
                "package %s after notification dispatch: %s",
                pkg_id,
                exc,
                exc_info=True,
            )

    counts["duration_seconds"] = round(time.monotonic() - started, 3)
    logger.info("post-deadline escalation complete: %s", counts)
    return counts


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    return await run_daily_post_deadline_escalation(db)


def register(scheduler) -> None:
    """Register the daily post-deadline escalation job.

    Fires once a day at 16:00 UTC — ≈ 9:00 AM Mountain Time, 1 hour offset
    from daily_insurance_expiration.
    """
    scheduler.add_job(
        _run,
        CronTrigger(hour=16, minute=0),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 16:00 UTC)", JOB_ID)
