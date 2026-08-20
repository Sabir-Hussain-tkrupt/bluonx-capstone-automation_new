"""
Daily bid-reminders job — sends T-7 / T-3 / T-0 bid-deadline reminders.

Each morning this job finds open bid packages whose deadline falls exactly
7, 3, or 0 days from today and emails the invited vendor contacts a
tier-appropriate reminder (friendly / urgent / final). Vendors submit through
the secure link in their original bid-invitation email — that magic-link
token stays valid until the deadline — so reminder emails carry no portal
link of their own.

The job is idempotent: an email_log dedup check skips any invitation that
already received a bid_reminder today, so a server restart or a coalesced
misfire never double-sends. Each send is also guarded by a fresh status
re-read, so an invitation submitted/declined between the bulk query and the
send is skipped.

PostgREST cannot express `deadline::date IN (CURRENT_DATE+7,+3,0)` (no casts,
no CURRENT_DATE), so the query selects a coarse 8-day deadline window and the
exact T-7 / T-3 / T-0 tier is derived per row in Python.

See backend/app/jobs/README.md for the job-authoring contract.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services.email_service import EmailService, create_email_provider
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

JOB_ID = "daily_bid_reminders"

# Invitation statuses that mean the vendor is done — no reminder is owed.
_EXCLUDED_STATUSES = ("submitted", "declined", "expired", "no_response")

# Concurrency cap for the send fan-out — keeps us within SES rate limits.
_SEND_CONCURRENCY = 10

# days-until-deadline -> (result counter key, template stem, subject prefix)
_TIERS: dict[int, tuple[str, str, str]] = {
    7: ("t_minus_7_sent", "bid_reminder_friendly", "Reminder: Bid due in 7 days"),
    3: ("t_minus_3_sent", "bid_reminder_urgent", "Urgent: Bid due in 3 days"),
    0: ("t_minus_0_sent", "bid_reminder_final", "Final Call: Bid due today"),
}


def _embed(row: dict, key: str) -> dict:
    """Unwrap a PostgREST to-one embedded resource.

    Embedded resources come back as a nested dict, but some PostgREST
    versions wrap a to-one relationship in a single-element list. Normalize
    both to a dict (empty dict if absent).
    """
    value = row.get(key)
    if isinstance(value, list):
        return value[0] if value else {}
    return value or {}


def _format_deadline(deadline_str: str) -> str:
    """Format an ISO deadline timestamp the same way the original
    bid-invitation email does (see bid_package_service._format_deadline)."""
    try:
        return datetime.fromisoformat(deadline_str).strftime(
            "%B %d, %Y at %I:%M %p UTC"
        )
    except (ValueError, TypeError):
        return deadline_str


async def _send_one_reminder(db, email_service, due: dict) -> str:
    """Send one reminder email. Returns the result-counter key to increment.

    Never raises — any failure is logged and counted as 'failed' so one bad
    invitation cannot sink the rest of the batch.
    """
    invitation_id = due["invitation_id"]
    try:
        # Fresh status re-read: the invitation may have been submitted or
        # declined between the bulk query and now.
        status_resp = (
            db.table("bid_invitations")
            .select("status")
            .eq("id", invitation_id)
            .maybe_single()
            .execute()
        )
        current = status_resp.data if status_resp else None
        if not current or current.get("status") in _EXCLUDED_STATUSES:
            return "skipped_status_changed"

        counter_key, stem, subject_prefix = _TIERS[due["delta"]]
        context = due["context"]
        html_body = template_renderer.render(f"{stem}.html", context)
        plain_text_body = template_renderer.render_text(f"{stem}.txt", context)
        subject = (
            f"{subject_prefix} — "
            f"{context['project_name']} / {context['task_name']}"
        )

        result = await email_service.send_email(
            to_email=due["to_email"],
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text_body,
            email_type="bid_reminder",
            recipient_type="vendor_contact",
            reference_type="bid_invitations",
            reference_id=invitation_id,
        )
        # EmailService already logged the failure row to email_log — do not
        # write a second one here, just tally it.
        if result.status == "failed":
            logger.warning(
                "bid reminder send failed for invitation %s: %s",
                invitation_id,
                result.error,
            )
            return "failed"
        return counter_key
    except Exception as exc:  # noqa: BLE001 — isolate one bad send from the batch
        logger.error(
            "bid reminder errored for invitation %s: %s",
            invitation_id,
            exc,
            exc_info=True,
        )
        return "failed"


async def run_daily_bid_reminders(db, email_service) -> dict:
    """Find bid invitations due in 7 / 3 / 0 days and email tiered reminders.

    `db` is a Supabase client and `email_service` an EmailService; both are
    injected so the job body can be exercised with test doubles.
    """
    started = time.monotonic()
    counts = {
        "t_minus_7_sent": 0,
        "t_minus_3_sent": 0,
        "t_minus_0_sent": 0,
        "failed": 0,
        "skipped_already_sent": 0,
        "skipped_status_changed": 0,
    }

    today = datetime.now(timezone.utc).date()
    day_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    # Coarse window: deadlines from today 00:00 up to (today+8) 00:00. The
    # exact tier is derived per row below.
    window_end = day_start + timedelta(days=8)

    # ── Query phase ─────────────────────────────────────────────────────
    resp = (
        db.table("bid_invitations")
        .select(
            "id, vendor_id, vendor_contact_id, bid_package_id, status, "
            "bid_packages!inner(deadline, status, created_by, "
            "tasks!inner(name, projects!inner(name)), "
            "users!created_by!inner(full_name, email)), "
            "vendor_contacts!inner(full_name, email), "
            "vendors!inner(company_name)"
        )
        .eq("bid_packages.status", "open")
        .not_.in_("status", list(_EXCLUDED_STATUSES))
        .gte("bid_packages.deadline", day_start.isoformat())
        .lt("bid_packages.deadline", window_end.isoformat())
        .execute()
    )
    rows = resp.data or []

    due: list[dict] = []
    for row in rows:
        pkg = _embed(row, "bid_packages")
        deadline_str = pkg.get("deadline")
        if not deadline_str:
            continue
        try:
            deadline_dt = datetime.fromisoformat(deadline_str)
        except (ValueError, TypeError):
            logger.warning(
                "bid reminder: unparseable deadline %r on invitation %s",
                deadline_str,
                row.get("id"),
            )
            continue
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        delta = (deadline_dt.astimezone(timezone.utc).date() - today).days
        if delta not in _TIERS:
            continue  # within the window but not a reminder day (1/2/4/5/6).

        task = _embed(pkg, "tasks")
        project = _embed(task, "projects")
        creator = _embed(pkg, "users")
        contact = _embed(row, "vendor_contacts")
        vendor = _embed(row, "vendors")
        due.append(
            {
                "invitation_id": row["id"],
                "delta": delta,
                "to_email": contact.get("email"),
                "context": {
                    "vendor_contact_name": contact.get("full_name"),
                    "task_name": task.get("name"),
                    "project_name": project.get("name"),
                    "bid_deadline": _format_deadline(deadline_str),
                    "pm_name": creator.get("full_name"),
                    "pm_email": creator.get("email"),
                    "company_name": vendor.get("company_name"),
                },
            }
        )

    # ── Dedup phase: skip invitations already reminded today ────────────
    candidate_ids = [d["invitation_id"] for d in due]
    already_sent: set = set()
    if candidate_ids:
        tomorrow_start = day_start + timedelta(days=1)
        log_resp = (
            db.table("email_log")
            .select("reference_id")
            .eq("email_type", "bid_reminder")
            .eq("reference_type", "bid_invitations")
            .in_("reference_id", candidate_ids)
            .gte("created_at", day_start.isoformat())
            .lt("created_at", tomorrow_start.isoformat())
            .execute()
        )
        already_sent = {r.get("reference_id") for r in (log_resp.data or [])}

    to_send: list[dict] = []
    for d in due:
        if d["invitation_id"] in already_sent:
            counts["skipped_already_sent"] += 1
        else:
            to_send.append(d)

    # ── Send phase: bounded concurrent fan-out ──────────────────────────
    if to_send:
        sem = asyncio.Semaphore(_SEND_CONCURRENCY)

        async def _bounded(d: dict) -> str:
            async with sem:
                return await _send_one_reminder(db, email_service, d)

        for key in await asyncio.gather(*(_bounded(d) for d in to_send)):
            counts[key] += 1

    counts["duration_seconds"] = round(time.monotonic() - started, 3)
    logger.info("bid reminders complete: %s", counts)
    return counts


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — wrapped by tracked_job for logging + last-run state."""
    db = get_supabase_client()
    email_service = EmailService(provider=create_email_provider(), db_client=db)
    return await run_daily_bid_reminders(db, email_service)


def register(scheduler) -> None:
    """Register the daily bid-reminders job.

    Fires once a day at 15:00 UTC. The intent is a morning send in BluOnX's
    local timezone: 15:00 UTC is 08:00 Mountain Standard Time (UTC-7) and
    09:00 Mountain Daylight Time (UTC-6). The cron hour is fixed in UTC, so
    the local send time drifts by an hour at each DST changeover. That ~1h
    seasonal drift is acceptable for MVP; if BluOnX needs the send pinned to
    an exact local hour, nudge this hour by 1 twice a year at the DST
    boundaries.
    """
    scheduler.add_job(
        _run,
        CronTrigger(hour=15, minute=0),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 15:00 UTC)", JOB_ID)
