"""
Insurance-expiration monitoring job — STUB (Task 7.1 foundation).

The full implementation lands in Task 7.4: a daily UTC CronTrigger that emails
admins a digest of vendor insurance certificates expiring at T-30 and T-7.
Until then this module only reserves the job ID and exposes a no-op register()
so the scheduler foundation can wire it in without errors.

See backend/app/jobs/README.md for the job-authoring contract.
"""

import logging

logger = logging.getLogger(__name__)

JOB_ID = "daily_insurance_expiration"


def register(scheduler) -> None:
    """No-op until Task 7.4 adds the CronTrigger and job body."""
    logger.info("Job %s not yet implemented (stub — see Task 7.4)", JOB_ID)
