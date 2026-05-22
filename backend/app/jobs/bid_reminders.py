"""
Daily bid-reminders job — STUB (Task 7.1 foundation).

The full implementation lands in Task 7.3: a daily UTC CronTrigger that sends
T-7 / T-3 / T-0 bid-deadline reminders to vendor contacts. Until then this
module only reserves the job ID and exposes a no-op register() so the
scheduler foundation can wire it in without errors.

See backend/app/jobs/README.md for the job-authoring contract.
"""

import logging

logger = logging.getLogger(__name__)

JOB_ID = "daily_bid_reminders"


def register(scheduler) -> None:
    """No-op until Task 7.3 adds the CronTrigger and job body."""
    logger.info("Job %s not yet implemented (stub — see Task 7.3)", JOB_ID)
