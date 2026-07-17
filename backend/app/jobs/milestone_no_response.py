"""
Milestone no-response escalation job (Phase 10.2).

The inbound half's safety net: a vendor check-in that goes unanswered for 3
WORKING days (weekends skipped) is escalated. The milestone moves
scheduled/in_progress → unresponsive via the authoritative transition, which
pauses its check-in cycle, and the owning PM gets an email + in-app alert so a
forgotten milestone can't sit frozen.

Locked rules:
  - 3 WORKING days (Mon–Fri) since the check-in was sent (working_days_since).
  - Once per check: skip if a no_response_alert row already exists for the
    milestone's current cycle, or the milestone already left scheduled/in_progress.
  - A BOUNCED (or complained/failed) check email is NOT silence: skip escalation
    and instead tell the PM to fix the vendor's address (a delivery-failed
    notification), so a bad address never masquerades as a non-responsive vendor.

This is the ONLY milestone scheduler job in scope for 10.2. The outbound daily
check-in send is Phase 10.3. See backend/app/jobs/README.md for the contract.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.supabase_client import get_supabase_client
from app.core.time import business_today, working_days_since
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services.email_service import EmailService, create_email_provider
from app.services.milestone_email_service import send_milestone_pm_alert_email
from app.services.milestone_notification_service import notify_milestone_unresponsive
from app.services.milestone_service import MilestoneError, escalate_no_response
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

JOB_ID = "milestone_no_response"

# Only these three alert kinds are vendor check-ins that can be escalated.
_VENDOR_CHECK_ALERT_TYPES = ("start_check", "progress_check", "completion_check")

# The milestone must still be actively awaiting a check-in. delayed/unresponsive
# already PAUSE the cycle (and aren't legal system_no_response sources);
# completed/cancelled are terminal.
_ESCALATABLE_STATUSES = ("scheduled", "in_progress")

# Working days of silence before escalation.
_WORKING_DAYS_THRESHOLD = 3

# email_log delivery states that mean the vendor never actually got the check-in.
_UNDELIVERED_STATUSES = ("bounced", "complained", "failed")

# alert_type → human label for the PM email copy.
_CHECK_LABELS = {
    "start_check": "start confirmation",
    "progress_check": "progress check",
    "completion_check": "completion confirmation",
}


def _embed_one(row: dict, key: str) -> dict:
    """Unwrap a PostgREST to-one embed (dict, or single-element list)."""
    value = row.get(key)
    if isinstance(value, list):
        return value[0] if value else {}
    return value or {}


def _sent_date(created_at: str | None) -> date | None:
    """The alert's send date in the business timezone, or None if unparseable.

    Anchored to the same clock as business_today() so the working-day count is
    consistent regardless of where the container runs.
    """
    if not created_at:
        return None
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(settings.BUSINESS_TIMEZONE)).date()


async def run_milestone_no_response_escalation(
    db, email_service, notification_creator=create_notification
) -> dict:
    """Escalate vendor check-ins silent for >= 3 working days. See module docstring.

    `db`, `email_service`, and `notification_creator` are injected so the body
    can be exercised with test doubles.
    """
    started = time.monotonic()
    today = business_today()
    counts = {
        "escalated": 0,
        "bounce_notified": 0,
        "skipped_not_due": 0,
        "skipped_answered": 0,
        "skipped_already_escalated": 0,
        "skipped_not_escalatable": 0,
        "skipped_stale_cycle": 0,
        "failed": 0,
    }

    # ── Query: vendor check-in alerts + their milestone + delivery status ────
    resp = (
        db.table("milestone_alerts")
        .select(
            "id, milestone_id, alert_type, cycle_number, created_at,"
            " milestones!inner(id, status, cycle_number, created_by),"
            " email_log(status)"
        )
        .eq("recipient_type", "vendor")
        .in_("alert_type", list(_VENDOR_CHECK_ALERT_TYPES))
        .execute()
    )
    alerts = resp.data or []
    if not alerts:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.info("milestone no-response: no vendor check-in alerts — %s", counts)
        return counts

    # ── Bulk pre-queries: answered alerts + already-escalated (milestone,cycle) ──
    alert_ids = [a["id"] for a in alerts]
    answered_ids: set[str] = set()
    for chunk_start in range(0, len(alert_ids), 200):
        chunk = alert_ids[chunk_start : chunk_start + 200]
        ans = (
            db.table("milestone_responses")
            .select("milestone_alert_id")
            .in_("milestone_alert_id", chunk)
            .execute()
        )
        answered_ids.update(r["milestone_alert_id"] for r in (ans.data or []))

    milestone_ids = list({a["milestone_id"] for a in alerts})
    escalated_pairs: set[tuple[str, int]] = set()
    for chunk_start in range(0, len(milestone_ids), 200):
        chunk = milestone_ids[chunk_start : chunk_start + 200]
        esc = (
            db.table("milestone_alerts")
            .select("milestone_id, cycle_number")
            .eq("alert_type", "no_response_alert")
            .in_("milestone_id", chunk)
            .execute()
        )
        for r in esc.data or []:
            if r.get("cycle_number") is not None:
                escalated_pairs.add((r["milestone_id"], r["cycle_number"]))

    # ── Evaluate + act ──────────────────────────────────────────────────────
    for alert in alerts:
        milestone = _embed_one(alert, "milestones")
        ms_status = milestone.get("status")
        ms_cycle = milestone.get("cycle_number")

        # Non-terminal, non-paused only.
        if ms_status not in _ESCALATABLE_STATUSES:
            counts["skipped_not_escalatable"] += 1
            continue
        # Only the current cycle's check-in is live.
        if alert.get("cycle_number") != ms_cycle:
            counts["skipped_stale_cycle"] += 1
            continue
        # Already answered → not silence.
        if alert["id"] in answered_ids:
            counts["skipped_answered"] += 1
            continue
        # Once per check (marker row for this milestone+cycle).
        if (alert["milestone_id"], ms_cycle) in escalated_pairs:
            counts["skipped_already_escalated"] += 1
            continue
        # 3 working days of silence.
        sent = _sent_date(alert.get("created_at"))
        if sent is None or working_days_since(sent, today) < _WORKING_DAYS_THRESHOLD:
            counts["skipped_not_due"] += 1
            continue

        # Bounce rule: a bounced check email is a delivery problem, not silence.
        delivery = _embed_one(alert, "email_log")
        if delivery.get("status") in _UNDELIVERED_STATUSES:
            _notify_delivery_failure(
                db, notification_creator, alert, milestone, delivery
            )
            counts["bounce_notified"] += 1
            continue

        key = await _escalate_one(db, email_service, alert, milestone, today)
        counts[key] += 1
        # Mark the pair so a duplicate alert in the same batch can't double-fire.
        if key == "escalated":
            escalated_pairs.add((alert["milestone_id"], ms_cycle))

    counts["duration_seconds"] = round(time.monotonic() - started, 3)
    logger.info("milestone no-response escalation complete: %s", counts)
    return counts


def _notify_delivery_failure(
    db, notification_creator, alert: dict, milestone: dict, delivery: dict
) -> None:
    """Tell the PM the check-in bounced (dedupe handles repeat runs)."""
    creator_id = milestone.get("created_by")
    if not creator_id:
        return
    label = _CHECK_LABELS.get(alert["alert_type"], "check-in")
    try:
        notification_creator(
            db,
            user_id=creator_id,
            notification_type="milestone_delivery_failed",
            title="Check-in email could not be delivered",
            message=(
                f"The {label} email for this milestone was reported "
                f"'{delivery.get('status')}'. Escalation is on hold — please "
                "verify the vendor's contact email."
            ),
            reference_type="milestones",
            reference_id=alert["milestone_id"],
            dedupe=True,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the batch
        logger.error(
            "milestone no-response: failed to notify delivery failure for "
            "milestone %s: %s",
            alert["milestone_id"],
            exc,
            exc_info=True,
        )


async def _escalate_one(db, email_service, alert: dict, milestone: dict, today) -> str:
    """Escalate one silent check-in. Returns a counter key. Never raises."""
    milestone_id = alert["milestone_id"]
    cycle = milestone.get("cycle_number")
    label = _CHECK_LABELS.get(alert["alert_type"], "check-in")
    sent = _sent_date(alert.get("created_at"))
    days_silent = working_days_since(sent, today) if sent else _WORKING_DAYS_THRESHOLD

    # 1. Authoritative transition → unresponsive. A PT409 (already moved between
    #    the query and now) means someone else handled it — skip, don't fail.
    try:
        escalate_no_response(
            milestone_id,
            milestone_alert_id=alert["id"],
            note=f"No vendor response to {label} after {days_silent} working days",
            db=db,
        )
    except MilestoneError as exc:
        if exc.status_code == 409:
            logger.info(
                "milestone no-response: milestone %s already moved; skipping",
                milestone_id,
            )
            return "skipped_already_escalated"
        logger.error(
            "milestone no-response: transition failed for milestone %s: %s",
            milestone_id,
            exc,
        )
        return "failed"

    # 2. The escalation happened. Side effects are best-effort — a failed email
    #    must not undo the transition or crash the batch.
    creator_id = milestone.get("created_by")
    if creator_id:
        try:
            await send_milestone_pm_alert_email(
                milestone_id=milestone_id,
                alert_type="no_response",
                recipient_user_id=creator_id,
                db=db,
                email_service=email_service,
                check_type_label=label,
                days_silent=days_silent,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "milestone no-response: PM email raised for milestone %s: %s",
                milestone_id,
                exc,
                exc_info=True,
            )
    try:
        notify_milestone_unresponsive(db, milestone_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "milestone no-response: in-app notify raised for milestone %s: %s",
            milestone_id,
            exc,
            exc_info=True,
        )

    # 3. Dedup marker: a no_response_alert row for this milestone + cycle, so a
    #    re-run (or a duplicate check alert) never escalates the same check twice.
    try:
        db.table("milestone_alerts").insert(
            {
                "milestone_id": milestone_id,
                "alert_type": "no_response_alert",
                "recipient_type": "pm",
                "cycle_number": cycle,
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "milestone no-response: failed to write dedup marker for milestone "
            "%s: %s",
            milestone_id,
            exc,
            exc_info=True,
        )

    return "escalated"


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    email_service = EmailService(provider=create_email_provider(), db_client=db)
    return await run_milestone_no_response_escalation(db, email_service)


def register(scheduler) -> None:
    """Register the daily milestone no-response escalation job.

    Fires at 16:30 UTC — staggered after post_deadline_escalation (16:00) so the
    daily jobs don't collide. ~9:30 AM Mountain Time.
    """
    scheduler.add_job(
        _run,
        CronTrigger(hour=16, minute=30),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 16:30 UTC)", JOB_ID)
