"""
Post-deadline escalation job — STUB (Task 7.1 foundation).

The full implementation lands in Task 7.5: a daily UTC CronTrigger that emails
each bid-package creator a digest of packages that closed in the last 24 hours
with non-responding vendors. Until then this module only reserves the job ID
and exposes a no-op register() so the scheduler foundation can wire it in
without errors.

See backend/app/jobs/README.md for the job-authoring contract.
"""

import logging

logger = logging.getLogger(__name__)

JOB_ID = "post_deadline_escalation"


def register(scheduler) -> None:
    """No-op until Task 7.5 adds the CronTrigger and job body."""
    logger.info("Job %s not yet implemented (stub — see Task 7.5)", JOB_ID)
