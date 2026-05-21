"""Tests for GET /api/v1/admin/scheduler-health."""

from app.jobs.scheduler import KNOWN_JOB_IDS, is_running, record_last_run

ENDPOINT = "/api/v1/admin/scheduler-health"


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


def test_unauthenticated_returns_403(client):
    """A request with no auth header is rejected (HTTPBearer convention: 403)."""
    resp = client.get(ENDPOINT)
    assert resp.status_code == 403
