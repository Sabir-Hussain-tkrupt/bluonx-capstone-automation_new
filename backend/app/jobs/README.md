# Scheduled jobs

Background jobs run inside the FastAPI process on a single `AsyncIOScheduler`
(see [`scheduler.py`](scheduler.py) and `docs/adr/0001-scheduler-single-instance.md`).
This is the authoring contract for every job in this directory. The hourly
[`revision_expiry`](revision_expiry.py) job is the reference implementation.

## Job-authoring contract

1. **One module per job.** Each job lives in its own file under `app/jobs/`
   and exposes a `register(scheduler)` function. Nothing else imports it.

2. **Decorate the entrypoint with `@tracked_job(JOB_ID)`** — defined in
   [`scheduler.py:73`](scheduler.py#L73). It logs start/complete, records the
   success/failure last-run state read by `/admin/scheduler-health`, and
   swallows exceptions so a failing job never crashes the scheduler. The
   decorated coroutine must **return a JSON-serializable dict** — it is
   surfaced verbatim in the health endpoint's `result` field.

3. **`scheduler.add_job(...)` must pass** `id=JOB_ID`, `replace_existing=True`,
   and `**DEFAULT_JOB_KWARGS` — the shared `{coalesce, misfire_grace_time,
   max_instances}` dict at [`scheduler.py:29`](scheduler.py#L29).

4. **Add `JOB_ID` to `KNOWN_JOB_IDS`** at [`scheduler.py:37`](scheduler.py#L37)
   so `/admin/scheduler-health` reports the job even before it first runs.

5. **Wire it into `start_scheduler()`** at [`scheduler.py:106`](scheduler.py#L106):
   a deferred import inside the function (avoids an import cycle — job modules
   import from `scheduler.py`) plus an explicit `register(scheduler)` call.

6. **Use a UTC `CronTrigger`.** The scheduler runs in UTC; never use a local
   timezone. Add a code comment stating the equivalent local fire time for
   the BluOnX team, e.g. `# 13:00 UTC = 08:00 America/Chicago`.

7. **Wrap batch/heavy work in `asyncio.gather` with an `asyncio.Semaphore(10)`**
   so per-item failures stay isolated and SES rate limits are respected.

8. **Email sends go through `EmailService.send_email()`** — never
   `send_bulk_emails()`, which bypasses `email_log`. Per-recipient failures
   are logged by the service; the job logs and continues.

## Minimal example

```python
"""My job — one-line description of what it transitions."""

import logging
from apscheduler.triggers.cron import CronTrigger

from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job

logger = logging.getLogger(__name__)
JOB_ID = "my_job"


async def do_work(db) -> dict:
    """Pure job body — unit-tested directly with the FakeSupabase double
    (see tests/jobs/conftest.py)."""
    ...
    return {"processed": 0}


@tracked_job(JOB_ID)
async def _run() -> dict:
    """Scheduler entrypoint — tracked_job adds logging + last-run state."""
    return await do_work(get_supabase_client())


def register(scheduler) -> None:
    """Register the job. Runs daily at 13:00 UTC (08:00 America/Chicago)."""
    scheduler.add_job(
        _run,
        CronTrigger(hour=13, minute=0),
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s", JOB_ID)
```

Then add `JOB_ID` to `KNOWN_JOB_IDS` and a deferred import +
`my_job.register(scheduler)` call inside `start_scheduler()`.

## Testing

Unit-test the job *body* directly against the `FakeSupabase` double from
[`tests/jobs/conftest.py`](../../../tests/jobs/conftest.py) — do not start the
real scheduler. The scheduler-health endpoint reads only in-memory state.

## Status

`bid_reminders`, `insurance_expiration`, `post_deadline_escalation`, and
`scheduler_self_check` are currently **stubs** (Task 7.1 foundation): their
`register()` is a no-op and they add no `CronTrigger`. The trigger and body
land in Tasks 7.3 / 7.4 / 7.5 / 7.7 respectively.
