"""
Milestone daily check-in job (Phase 10.3).

The outbound half of milestone tracking: each morning this job asks vendors the
one question their milestone is waiting on, by minting a portal token and
emailing a start / progress / completion check.

Locked rules:
  - Start check on start_date; completion check on end_date. Both always apply.
  - Progress check is END-anchored: it fires _PROGRESS_CHECK_LEAD_DAYS before
    end_date, and only if that date leaves _MIN_GAP_DAYS of breathing room after
    the start. That gate IS the "does this milestone need a progress check" test
    (short milestones get only start + completion); the effective minimum length
    for a progress check is 8 days.
  - A check date already in the PAST never fires. A milestone that materialized
    mid-window simply misses that check rather than getting a backdated blast.
  - Only scheduled/in_progress are sendable. delayed/unresponsive PAUSE the cycle
    (a human owes an answer, not the vendor); completed/cancelled are terminal.
  - A one-day milestone (start_date == end_date) legitimately gets BOTH a start
    and a completion check: they are different questions, and the vendor's
    completion 'yes' is only legal from in_progress, so skipping the start check
    would strand the milestone in 'scheduled' and reject the vendor's answer.

There is no UNIQUE on (milestone, alert_type, cycle_number), since alerts
legitimately recur across cycles, so idempotency is by QUERY: a bulk pre-query
builds the already-sent set, and each send re-reads the milestone's live status + cycle
immediately before minting. mint_checkin_token writes the alert row BEFORE the
email goes out, which is what makes that row a usable dedup marker. Combined with
coalesce=True + max_instances=1, a restart or misfire pile-up never double-sends.

Each send stamps milestone_alerts.email_log_id with the row EmailService wrote.
That FK is what lets the milestone_no_response job tell a BOUNCE apart from vendor
silence; without it a bounced check-in escalates the vendor to 'unresponsive' and
tells the PM they went dark. A failed/undelivered send is linked for the same
reason, and its alert row is never deleted: the row is the dedup marker, and a
retry is governed by the next cycle.

See backend/app/jobs/README.md for the job-authoring contract.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.core.time import business_today
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services.email_service import EmailService, create_email_provider
from app.services.milestone_email_service import send_milestone_check_email
from app.services.milestone_service import MilestoneError
from app.services.milestone_token_service import mint_checkin_token

logger = logging.getLogger(__name__)

JOB_ID = "milestone_daily_checkin"

# The progress check fires this many days before end_date.
_PROGRESS_CHECK_LEAD_DAYS = 5

# Minimum breathing room between the start and the progress check for that check
# to be worth sending. Effective minimum milestone length for a progress check is
# _PROGRESS_CHECK_LEAD_DAYS + _MIN_GAP_DAYS = 8 days.
_MIN_GAP_DAYS = 3

# Concurrency cap for the send fan-out, to stay within SES rate limits.
_SEND_CONCURRENCY = 10

# The milestone must still be actively awaiting a check-in.
_SENDABLE_STATUSES = ("scheduled", "in_progress")

# alert_type (DB enum) -> check_type (the email helper's short form).
_CHECK_SHORT = {
    "start_check": "start",
    "progress_check": "progress",
    "completion_check": "completion",
}

# alert_type -> result-counter key.
_SENT_COUNTER = {
    "start_check": "start_sent",
    "progress_check": "progress_sent",
    "completion_check": "completion_sent",
}

# PostgREST .in_() batch size for the bulk pre-query.
_CHUNK = 200


def _parse_date(value) -> date | None:
    """Parse a view date ('2026-07-15') to a date, or None if absent/unparseable."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _due_checks(start_date: date, end_date: date, today: date) -> list[str]:
    """The alert_types due TODAY for one milestone, in send order.

    Every comparison is a strict `== today`, which is the catch-up guard: a check
    date in the past is simply missed, never fired retroactively.

    A one-day milestone (start_date == end_date) returns BOTH a start and a
    completion check. That is deliberate: they ask different questions, and the
    vendor's completion 'yes' is only legal from in_progress, so skipping the
    start check would strand the milestone in 'scheduled' and reject the answer.
    The progress check can never collide with either, because its gate puts it at least
    _MIN_GAP_DAYS after the start and _PROGRESS_CHECK_LEAD_DAYS before the end.
    """
    due: list[str] = []

    if start_date == today:
        due.append("start_check")

    progress_date = end_date - timedelta(days=_PROGRESS_CHECK_LEAD_DAYS)
    if today == progress_date and (progress_date - start_date).days >= _MIN_GAP_DAYS:
        due.append("progress_check")

    if end_date == today:
        due.append("completion_check")

    return due


def _link_alert_to_log(db, candidate: dict, log_id: str) -> None:
    """Stamp the just-minted check-in alert with the email_log row it was sent in.

    mint_checkin_token returns (raw_token, portal_url), not the alert id, so the
    update targets the dedup key instead, which identifies exactly the row just
    written. Best-effort: a milestone whose alert we cannot link still sent, and a
    missing link only costs the no-response job its bounce signal.
    """
    try:
        (
            db.table("milestone_alerts")
            .update({"email_log_id": log_id})
            .eq("milestone_id", candidate["milestone_id"])
            .eq("alert_type", candidate["alert_type"])
            .eq("cycle_number", candidate["cycle_number"])
            .eq("recipient_type", "vendor")
            .execute()
        )
    except Exception as exc:  # noqa: BLE001: never sink a send that already happened
        logger.error(
            "milestone check-in: failed to link alert to email_log %s for "
            "milestone %s (%s): %s",
            log_id,
            candidate["milestone_id"],
            candidate["alert_type"],
            exc,
            exc_info=True,
        )


async def _send_one_check(db, email_service, candidate: dict) -> str:
    """Mint + send one check-in. Returns a counter key. Never raises."""
    milestone_id = candidate["milestone_id"]
    alert_type = candidate["alert_type"]
    cycle = candidate["cycle_number"]
    try:
        # Fresh re-read: the milestone may have been completed, paused, or
        # rescheduled (cycle bump) between the bulk query and now.
        resp = (
            db.table("milestones")
            .select("status, cycle_number")
            .eq("id", milestone_id)
            .maybe_single()
            .execute()
        )
        current = resp.data if resp else None
        if not current or current.get("status") not in _SENDABLE_STATUSES:
            return "skipped_status_changed"
        if current.get("cycle_number") != cycle:
            # A bump means this candidate's alert_type/cycle is already stale.
            return "skipped_status_changed"

        # Creates the milestone_alerts row (the dedup marker) AND the token.
        _raw_token, portal_url = mint_checkin_token(
            db,
            milestone_id=milestone_id,
            alert_type=alert_type,
            cycle_number=cycle,
        )

        result = await send_milestone_check_email(
            milestone_id=milestone_id,
            check_type=_CHECK_SHORT[alert_type],
            portal_url=portal_url,
            db=db,
            email_service=email_service,
        )

        # Link first, status second: an undelivered send needs its log row linked
        # just as much as a delivered one (see module docstring).
        if result is not None and result.log_id:
            _link_alert_to_log(db, candidate, result.log_id)

        if result is None or result.status != "sent":
            logger.warning(
                "milestone check-in: %s send failed for milestone %s: %s",
                alert_type,
                milestone_id,
                getattr(result, "error", "not sent"),
            )
            return "failed"
        return _SENT_COUNTER[alert_type]
    except MilestoneError as exc:
        # No contract vendor / no primary contact to send to.
        logger.warning(
            "milestone check-in: cannot mint %s for milestone %s: %s",
            alert_type,
            milestone_id,
            exc,
        )
        return "failed"
    except Exception as exc:  # noqa: BLE001: isolate one bad send from the batch
        logger.error(
            "milestone check-in: %s errored for milestone %s: %s",
            alert_type,
            milestone_id,
            exc,
            exc_info=True,
        )
        return "failed"


async def run_milestone_daily_checkin(db, email_service) -> dict:
    """Send today's vendor start / progress / completion check-ins.

    `db` and `email_service` are injected so the body can be exercised with test
    doubles.
    """
    started = time.monotonic()
    today = business_today()
    counts = {
        "start_sent": 0,
        "progress_sent": 0,
        "completion_sent": 0,
        "failed": 0,
        "skipped_already_sent": 0,
        "skipped_status_changed": 0,
    }

    # ── Query phase ─────────────────────────────────────────────────────
    # v_milestone_overview is the same read surface the dashboard uses (and is
    # already granted to service_role). PostgREST cannot express the date
    # arithmetic, so the due check is derived per row below, as bid_reminders
    # derives its T-7/T-3/T-0 tier.
    resp = (
        db.table("v_milestone_overview")
        .select("milestone_id, status, cycle_number, start_date, end_date")
        .in_("status", list(_SENDABLE_STATUSES))
        .execute()
    )
    rows = resp.data or []

    candidates: list[dict] = []
    for row in rows:
        milestone_id = row.get("milestone_id")
        cycle = row.get("cycle_number")
        if not milestone_id or cycle is None:
            continue
        # Both columns are NOT NULL, so a None here means an unreadable value.
        # Skip rather than reason about a milestone with a broken date.
        start_date = _parse_date(row.get("start_date"))
        end_date = _parse_date(row.get("end_date"))
        if start_date is None or end_date is None:
            logger.warning(
                "milestone check-in: milestone %s has unreadable dates "
                "(start=%r end=%r); skipping",
                milestone_id,
                row.get("start_date"),
                row.get("end_date"),
            )
            continue
        for alert_type in _due_checks(start_date, end_date, today):
            candidates.append(
                {
                    "milestone_id": milestone_id,
                    "alert_type": alert_type,
                    "cycle_number": cycle,
                }
            )

    if not candidates:
        counts["duration_seconds"] = round(time.monotonic() - started, 3)
        logger.info("milestone check-in: nothing due today: %s", counts)
        return counts

    # ── Dedup phase ─────────────────────────────────────────────────────
    # mint_checkin_token writes the alert row before sending, so an existing row
    # for this (milestone, alert_type, cycle) means the check already went out.
    milestone_ids = list({c["milestone_id"] for c in candidates})
    already_sent: set[tuple[str, str, int]] = set()
    for chunk_start in range(0, len(milestone_ids), _CHUNK):
        chunk = milestone_ids[chunk_start : chunk_start + _CHUNK]
        sent_resp = (
            db.table("milestone_alerts")
            .select("milestone_id, alert_type, cycle_number")
            .eq("recipient_type", "vendor")
            .in_("alert_type", list(_CHECK_SHORT))
            .in_("milestone_id", chunk)
            .execute()
        )
        for r in sent_resp.data or []:
            already_sent.add((r["milestone_id"], r["alert_type"], r["cycle_number"]))

    to_send: list[dict] = []
    for c in candidates:
        key = (c["milestone_id"], c["alert_type"], c["cycle_number"])
        if key in already_sent:
            counts["skipped_already_sent"] += 1
        else:
            to_send.append(c)

    # ── Send phase: bounded concurrent fan-out ──────────────────────────
    if to_send:
        sem = asyncio.Semaphore(_SEND_CONCURRENCY)

        async def _bounded(c: dict) -> str:
            async with sem:
                return await _send_one_check(db, email_service, c)

        for key in await asyncio.gather(*(_bounded(c) for c in to_send)):
            counts[key] += 1

    counts["duration_seconds"] = round(time.monotonic() - started, 3)
    logger.info("milestone daily check-in complete: %s", counts)
    return counts


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint, wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    email_service = EmailService(provider=create_email_provider(), db_client=db)
    return await run_milestone_daily_checkin(db, email_service)


def register(scheduler) -> None:
    """Register the daily milestone check-in job.

    Fires at 16:15 UTC, the open slot between insurance_expiration (15:15) and
    milestone_no_response (16:30), so the daily jobs don't collide. 16:15 UTC =
    11:15 America/Chicago (CDT) / 10:15 (CST).
    """
    scheduler.add_job(
        _run,
        CronTrigger(hour=16, minute=15),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 16:15 UTC)", JOB_ID)
