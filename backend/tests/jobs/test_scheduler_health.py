"""Tests for GET /api/v1/admin/scheduler-health."""

from app.jobs.scheduler import (
    KNOWN_JOB_IDS,
    is_running,
    record_last_run,
    scheduler,
    start_scheduler,
    stop_scheduler,
)

ENDPOINT = "/api/v1/admin/scheduler-health"

# The five jobs the scheduler foundation must surface: the original hourly
# revision_expiry plus the four Phase 7 stubs registered in Task 7.1.
EXPECTED_JOB_IDS = {
    "revision_expiry",
    "daily_bid_reminders",
    "daily_insurance_expiration",
    "post_deadline_escalation",
    "scheduler_self_check",
}


def test_no_jobs_run_yet_returns_null_state(authed_client, clear_last_run):
    """Before any job runs, each registered job reports null last-run state."""
    resp = authed_client.get(ENDPOINT)
    assert resp.status_code == 200

    body = resp.json()
    assert set(body["jobs"].keys()) == set(KNOWN_JOB_IDS)
    for job_id in KNOWN_JOB_IDS:
        entry = body["jobs"][job_id]
        assert entry == {
            "last_run_at": None,
            "status": None,
            "result": None,
            "error": None,
        }

    # scheduler_running reflects the actual scheduler state (off in tests).
    assert body["scheduler_running"] == is_running()


def test_reports_recorded_run_state(authed_client, clear_last_run):
    """After a job records a success, the endpoint surfaces that state."""
    record_last_run(
        "revision_expiry", status="success", result={"expired_count": 2}
    )

    resp = authed_client.get(ENDPOINT)
    assert resp.status_code == 200

    entry = resp.json()["jobs"]["revision_expiry"]
    assert entry["status"] == "success"
    assert entry["result"] == {"expired_count": 2}
    assert entry["error"] is None
    assert entry["last_run_at"] is not None


def test_all_phase7_jobs_present(authed_client, clear_last_run):
    """All five jobs (revision_expiry + four Phase 7 stubs) appear in the
    health response with null last-run state before anything has run."""
    resp = authed_client.get(ENDPOINT)
    assert resp.status_code == 200

    body = resp.json()
    assert set(body["jobs"].keys()) == EXPECTED_JOB_IDS
    for job_id in EXPECTED_JOB_IDS:
        assert body["jobs"][job_id] == {
            "last_run_at": None,
            "status": None,
            "result": None,
            "error": None,
        }


async def test_start_scheduler_registers_jobs():
    """start_scheduler() runs every job's register() without raising.
    revision_expiry, daily_bid_reminders, and daily_insurance_expiration
    have real triggers today; the remaining Phase 7 stubs are no-ops, so
    scheduler.get_jobs() returns exactly those three entries after start.

    Async so AsyncIOScheduler.start() has a running event loop to bind to.
    """
    if scheduler.running:
        stop_scheduler()  # ensure a cold start so every register() runs

    start_scheduler()
    try:
        assert scheduler.running
        assert {job.id for job in scheduler.get_jobs()} == {
            "revision_expiry",
            "daily_bid_reminders",
            "daily_insurance_expiration",
        }
    finally:
        # Leave the scheduler stopped — the session `client` fixture's
        # lifespan does its own cold start in its own event loop.
        stop_scheduler()


def test_unauthenticated_returns_403(client):
    """A request with no auth header is rejected (HTTPBearer convention: 403)."""
    resp = client.get(ENDPOINT)
    assert resp.status_code == 403
