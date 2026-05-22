"""
Scheduler self-check job — STUB (Task 7.1 foundation).

The full implementation lands in Task 7.7: a daily UTC CronTrigger that
inspects the in-memory last-run state of every tracked job and emails admins
when one is stale beyond its expected interval. Until then this module only
reserves the job ID and exposes a no-op register() so the scheduler
foundation can wire it in without errors.

See backend/app/jobs/README.md for the job-authoring contract.
"""

import logging

logger = logging.getLogger(__name__)

JOB_ID = "scheduler_self_check"


def register(scheduler) -> None:
    """No-op until Task 7.7 adds the CronTrigger and job body."""
    logger.info("Job %s not yet implemented (stub — see Task 7.7)", JOB_ID)
