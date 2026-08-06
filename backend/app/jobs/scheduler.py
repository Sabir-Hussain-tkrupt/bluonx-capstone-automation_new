"""
APScheduler lifecycle + in-memory last-run tracking.

A single AsyncIOScheduler runs background jobs as coroutines on the app's
event loop. AsyncIOScheduler (not BackgroundScheduler) is a simplicity
choice: no worker-thread pool to size, and jobs reuse the singleton Supabase
client on the loop. It is not a thread-safety constraint — that client is
thread-safe for our usage, which is why the request path offloads blocking
calls via run_in_threadpool (see the ADR's 2026-06-12 note).

The scheduler is started/stopped by the FastAPI lifespan. Last-run state is
held in memory only — /admin/scheduler-health must be able to report whether
the scheduler is healthy even when the database is down.

See docs/adr/0001-scheduler-single-instance.md.
"""

import functools
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Module-level singleton. Created here; start_scheduler()/stop_scheduler()
# mutate its state. Never instantiate per-request.
scheduler = AsyncIOScheduler(timezone="UTC")

# Applied to every job at registration time.
DEFAULT_JOB_KWARGS = {
    "coalesce": True,
    "misfire_grace_time": 300,
    "max_instances": 1,
}

# Stable list of job ids — drives /admin/scheduler-health even when the
# scheduler was never started (e.g. under pytest). Add new job ids here.
KNOWN_JOB_IDS = (
    "revision_expiry",
    "daily_bid_reminders",
    "daily_insurance_expiration",
    "post_deadline_escalation",
    "milestone_daily_checkin",
    "milestone_no_response",
    "holiday_seed",
    "scheduler_self_check",
)

# job_id -> {"last_run_at", "status", "result", "error"}. In-memory only.
_last_run: dict[str, dict] = {}

# When the running scheduler last entered start_scheduler(). Drives the
# cold-start grace window in scheduler_self_check — a job that has never
# fired isn't stale until the scheduler has been up long enough for it
# to have had a real chance to run.
_started_at: datetime | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_last_run(job_id: str, *, status: str, result=None, error=None) -> None:
    """Record the outcome of a job's most recent execution (in memory)."""
    _last_run[job_id] = {
        "last_run_at": _utc_now_iso(),
        "status": status,
        "result": result,
        "error": error,
    }


def get_last_run(job_id: str) -> dict | None:
    """Return the last-run record for a job, or None if it never ran."""
    return _last_run.get(job_id)


def get_scheduler_started_at() -> datetime | None:
    """When the running scheduler last entered start_scheduler() (UTC), or None if stopped."""
    return _started_at


def is_running() -> bool:
    """Whether the scheduler is currently running."""
    return scheduler.running


def tracked_job(job_id: str):
    """
    Decorator for async job functions.

    Wraps the body in the shared try/except + logging + last-run recording
    so each job doesn't reimplement it. The decorated coroutine should
    return a JSON-serializable dict describing its result.

    Exceptions are logged at ERROR with a traceback and recorded as a
    failure, but NEVER re-raised — a failing job must not crash the
    scheduler. Structured logging is the production safety net (no Sentry
    today).
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            logger.info("%s job started", job_id)
            try:
                result = await fn(*args, **kwargs)
                record_last_run(job_id, status="success", result=result)
                logger.info("%s job complete: %s", job_id, result)
                return result
            except Exception as exc:  # noqa: BLE001 — must not escape the scheduler
                logger.error("%s job failed: %s", job_id, exc, exc_info=True)
                record_last_run(job_id, status="failure", error=str(exc))
                return None

        return wrapper

    return decorator


def start_scheduler() -> None:
    """
    Register all jobs and start the scheduler. Idempotent — safe to call
    twice. Called from the FastAPI lifespan on startup.
    """
    if scheduler.running:
        logger.info("Scheduler already running; start_scheduler() is a no-op")
        return

    # Deferred import avoids an import cycle: job modules import
    # tracked_job / DEFAULT_JOB_KWARGS from this module.
    from app.jobs import (
        bid_reminders,
        holiday_seed,
        insurance_expiration,
        milestone_daily_checkin,
        milestone_no_response,
        post_deadline_escalation,
        revision_expiry,
        scheduler_self_check,
    )

    revision_expiry.register(scheduler)
    bid_reminders.register(scheduler)
    insurance_expiration.register(scheduler)
    post_deadline_escalation.register(scheduler)
    milestone_daily_checkin.register(scheduler)
    milestone_no_response.register(scheduler)
    holiday_seed.register(scheduler)
    scheduler_self_check.register(scheduler)

    global _started_at
    _started_at = datetime.now(timezone.utc)
    scheduler.start()
    logger.info("Scheduler started (timezone=UTC)")


def stop_scheduler() -> None:
    """Gracefully stop the scheduler, waiting for running jobs to finish."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
    global _started_at
    _started_at = None
