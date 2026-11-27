"""Daily finance summary (Phase 6 · Task 6.6).

Retries hand-off emails that failed, then emails finance the payments approved
in the last 24 hours plus every hand-off not yet exported, with a CSV attached.
See README.md for the job contract.
"""

from __future__ import annotations

import logging

from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services import payment_notifications

logger = logging.getLogger(__name__)

JOB_ID = "finance_daily_summary"


@tracked_job(JOB_ID)
async def _run() -> dict:
    db = get_supabase_client()
    return await payment_notifications.daily_summary(db, payment_notifications.email_service(db))


def register(scheduler) -> None:
    """Daily at 13:00 UTC (6:00 AM Mountain Standard Time), before finance starts."""
    scheduler.add_job(
        _run,
        CronTrigger(hour=13, minute=0),  # 13:00 UTC = 06:00 America/Denver (MST)
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 13:00 UTC)", JOB_ID)
