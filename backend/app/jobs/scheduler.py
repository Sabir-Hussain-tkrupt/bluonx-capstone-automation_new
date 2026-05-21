"""
APScheduler lifecycle + in-memory last-run tracking.

A single AsyncIOScheduler runs background jobs as coroutines on the app's
event loop. AsyncIOScheduler (not BackgroundScheduler) is deliberate: the
sync Supabase client is not thread-safe, so jobs must run on the existing
loop, not in worker threads.

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
KNOWN_JOB_IDS = ("revision_expiry",)

# job_id -> {"last_run_at", "status", "result", "error"}. In-memory only.
_last_run: dict[str, dict] = {}


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

    # Deferred import avoids an import cycle: revision_expiry imports
    # tracked_job / DEFAULT_JOB_KWARGS from this module.
    from app.jobs import revision_expiry

    revision_expiry.register(scheduler)

    scheduler.start()
    logger.info("Scheduler started (timezone=UTC)")


def stop_scheduler() -> None:
    """Gracefully stop the scheduler, waiting for running jobs to finish."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
