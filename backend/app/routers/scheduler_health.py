"""Scheduler health endpoint — GET /api/v1/admin/scheduler-health

Surfaces in-memory last-run state per registered scheduled job for external
monitoring (e.g. an UptimeRobot canary). Reads no database — it must be able
to report scheduler health even if the database is down.
"""

from fastapi import APIRouter, Depends

from app.core.auth import get_current_active_user
from app.jobs.scheduler import KNOWN_JOB_IDS, get_last_run, is_running

router = APIRouter()

# Shape returned for a job that has never executed.
_NULL_RUN = {"last_run_at": None, "status": None, "result": None, "error": None}


@router.get("/admin/scheduler-health")
async def scheduler_health(
    user: dict = Depends(get_current_active_user),
) -> dict:
    """Report last-run state for each registered scheduled job."""
    jobs = {
        job_id: (get_last_run(job_id) or dict(_NULL_RUN))
        for job_id in KNOWN_JOB_IDS
    }
    return {"jobs": jobs, "scheduler_running": is_running()}
