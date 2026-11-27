"""Daily contingency health sweep (Phase 5 · Task 5.5).

Recalculates every baselined project, sends alerts that were never sent and
escalates the ones left undecided. Changes recalculate immediately on their own;
this catches anything a failed hook missed. See README.md for the job contract.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from starlette.concurrency import run_in_threadpool

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services import financial_alert_notifications as notify
from app.services import financial_health_service as svc

logger = logging.getLogger(__name__)

JOB_ID = "financial_health_sweep"
_PAGE = 500


def _project_ids(db) -> list[str]:
    ids: list[str] = []
    while True:
        batch = (
            db.table("projects").select("id").eq("budget_status", "baselined")
            .is_("deleted_at", "null").is_("archived_at", "null")
            .order("id").range(len(ids), len(ids) + _PAGE - 1).execute()
        ).data or []
        ids.extend(str(r["id"]) for r in batch)
        if len(batch) < _PAGE:
            return ids


async def run_financial_health_sweep(db, email_service) -> dict:
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    counts = {"projects": 0, "opened": 0, "sent": 0, "escalated": 0, "failed": 0}
    limit = asyncio.Semaphore(10)

    async def one(project_id: str) -> None:
        async with limit:
            try:
                opened = await run_in_threadpool(svc.recalculate, db, project_id)
                result = await notify.sweep_project(db, email_service, project_id, now)
                counts["projects"] += 1
                counts["opened"] += len(opened)
                counts["sent"] += result["sent"]
                counts["escalated"] += result["escalated"]
            except Exception:  # noqa: BLE001 - one project must not stop the others
                counts["failed"] += 1
                logger.exception("Financial health sweep: project %s failed", project_id)

    ids = await run_in_threadpool(_project_ids, db)
    await asyncio.gather(*(one(i) for i in ids))
    counts["duration_seconds"] = round(time.monotonic() - started, 3)
    # A run where nothing worked is a failure in scheduler health, not a success.
    if ids and counts["failed"] == len(ids):
        raise RuntimeError(f"All {len(ids)} projects failed")
    return counts


@tracked_job(JOB_ID)
async def _run() -> dict:
    db = get_supabase_client()
    return await run_financial_health_sweep(db, notify.email_service(db))


def register(scheduler) -> None:
    """Daily at 14:30 UTC (7:30 AM Mountain Standard Time)."""
    scheduler.add_job(
        _run,
        CronTrigger(hour=14, minute=30),  # 14:30 UTC = 07:30 America/Denver (MST)
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 14:30 UTC)", JOB_ID)
