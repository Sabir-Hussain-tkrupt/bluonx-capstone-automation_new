"""
Task 9.2 — award-create write path + validation override gate.

The server recomputes the 9.1 validation fresh (never trusts a client snapshot)
and gates the write:

  block            → 422 (returns the result; not overridable)
  warn + no/blank justification → 422 (returns the full result; forces the dialog)
  warn + justification          → 201, has_override=TRUE  + snapshot
  all clean                     → 201, has_override=FALSE + snapshot

Plus structural preconditions: 404 unknown submission, 422 wrong package status,
409 second active award per task. award_amount / task_id / vendor_id / awarded_by
are server-derived — the request carries only the submission + override fields.
"""

from __future__ import annotations

from uuid import uuid4

from postgrest.exceptions import APIError

from .conftest import PM_USER_ID, SUBMISSION_ID, TASK_ID, VENDOR_ID, award_body

URL = "/api/v1/awards"

# Local: the bid_packages.id the chain row carries, used by the pending-revision guard.
PACKAGE_ID = uuid4()


# ── Row builders ─────────────────────────────────────────────────────────


def chain_row(
    *,
    is_superseded: bool = False,
    is_draft: bool = False,
    status: str = "submitted",
    total_amount: str | None = "50000.00",
    package_status: str = "closed",
    budget_estimate: str | None = "50000.00",
    insurance_expiration: str | None = "2099-12-31",
    bonding_capacity: str | None = "100000.00",
    max_active_jobs: int | None = 10,
    current_active_jobs: int = 1,
    desired_start_date: str | None = None,
    proposed_start_date: str | None = None,
    estimated_end_date: str | None = None,
) -> dict:
    """The nested bid_submissions → … → projects row the 9.1 loader selects.
    Defaults are an all-clean, awardable candidate on a `closed` package."""
    return {
        "total_amount": total_amount,
        "proposed_start_date": proposed_start_date,
        "vendor_id": str(VENDOR_ID),
        "is_draft": is_draft,
        "is_superseded": is_superseded,
        "status": status,
        "is_direct_assign": False,
        "vendors": {
            "insurance_expiration_date": insurance_expiration,
            "bonding_capacity": bonding_capacity,
            "max_active_jobs": max_active_jobs,
            "current_active_jobs": current_active_jobs,
            "onboarding_status": "approved",
        },
        "bid_invitations": {
            "bid_packages": {
                "id": str(PACKAGE_ID),
                "desired_start_date": desired_start_date,
                "deadline": "2099-01-01",
                "status": package_status,
                "tasks": {
                    "id": str(TASK_ID),
                    "budget_estimate": budget_estimate,
                    "project_id": str(uuid4()),
                    "projects": {"estimated_end_date": estimated_end_date},
                },
            },
        },
    }


def award_row(**over) -> dict:
    """A canned, fully-populated awards row for the insert to read back
    (satisfies AwardResponse). Server-derived values asserted via the recorded
    insert payload, not this echo."""
    now = "2026-06-11T00:00:00+00:00"
    row = {
        "id": str(uuid4()),
        "task_id": str(TASK_ID),
        "bid_submission_id": str(SUBMISSION_ID),
        "vendor_id": str(VENDOR_ID),
        "awarded_by": str(PM_USER_ID),
        "awarded_at": now,
        "award_amount": "50000.00",
        "has_override": False,
        "override_justification": None,
        "validation_results": {},
        "contract_valid_days": 365,
        "work_duration_days": None,
        "status": "pending_acceptance",
        "created_at": now,
        "updated_at": now,
    }
    row.update(over)
    return row


def clean_spec(**chain_over) -> dict:
    # The award + task flip are written atomically through the fn_create_award
    # RPC, so the canned write lives under "rpc", not separate table ops.
    return {
        "bid_submissions": {"select": [chain_row(**chain_over)]},
        "rpc": {"fn_create_award": [award_row()]},
    }


# ── All-clean → 201, has_override=FALSE + snapshot ───────────────────────


def test_clean_award_writes_pending_acceptance(recording_client_factory):
    c, calls = recording_client_factory(clean_spec())
    r = c.post(URL, json=award_body())
    assert r.status_code == 201
    assert r.json()["status"] == "pending_acceptance"

    # The atomic write goes through fn_create_award; assert the server-derived
    # params. (The task → 'awarded' flip is now inside the DB function's
    # transaction, so it's no longer observable here — that's the point of the
    # atomicity fix; it's covered by the function itself.)
    params = calls["rpc"]["fn_create_award"]
    assert params["p_has_override"] is False
    assert params["p_override_justification"] is None
    # Server-derived, never from the client body.
    assert params["p_award_amount"] == "50000.00"
    assert params["p_task_id"] == str(TASK_ID)
    assert params["p_vendor_id"] == str(VENDOR_ID)
    assert params["p_awarded_by"] == str(PM_USER_ID)
    # Snapshot passed to the write on every award, clean or not.
    snap = params["p_validation_results"]
    assert snap["has_blocking"] is False and snap["has_warnings"] is False
    assert snap["rubric_version"] == "preaward-v1"


def test_clean_award_ignores_client_supplied_override(recording_client_factory):
    """has_override is never TRUE when no warnings existed, regardless of input."""
    c, calls = recording_client_factory(clean_spec())
    r = c.post(URL, json=award_body(has_override=True, override_justification="n/a"))
    assert r.status_code == 201
    params = calls["rpc"]["fn_create_award"]
    assert params["p_has_override"] is False
    assert params["p_override_justification"] is None


# ── contract-term params (Task 9.8) ──────────────────────────────────────


def test_award_persists_contract_term_params(recording_client_factory):
    """PM-set contract_valid_days + work_duration_days flow through the RPC,
    exactly as instructions do (server threads them into fn_create_award)."""
    c, calls = recording_client_factory(clean_spec())
    r = c.post(URL, json=award_body(contract_valid_days=730, work_duration_days=21))
    assert r.status_code == 201
    params = calls["rpc"]["fn_create_award"]
    assert params["p_contract_valid_days"] == 730
    assert params["p_work_duration_days"] == 21


def test_award_defaults_contract_valid_days_to_365(recording_client_factory):
    """Omitting validity persists the 1-year default; duration stays NULL."""
    c, calls = recording_client_factory(clean_spec())
    r = c.post(URL, json=award_body())
    assert r.status_code == 201
    params = calls["rpc"]["fn_create_award"]
    assert params["p_contract_valid_days"] == 365
    assert params["p_work_duration_days"] is None


# ── warn → override gate ─────────────────────────────────────────────────


def _warn_spec(**over) -> dict:
    # budget_estimate well below the award amount → budget_variance WARN.
    return clean_spec(budget_estimate="10000.00", **over)


def test_warn_without_justification_returns_422_with_result(client_factory):
    c = client_factory(_warn_spec())
    r = c.post(URL, json=award_body())
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["requires_override"] is True
    assert detail["has_warnings"] is True
    assert detail["has_blocking"] is False
    assert detail["can_award"] is True


def test_warn_blank_justification_returns_422(client_factory):
    c = client_factory(_warn_spec())
    r = c.post(URL, json=award_body(has_override=True, override_justification="   "))
    assert r.status_code == 422
    assert r.json()["detail"]["requires_override"] is True


def test_warn_with_justification_writes_override(recording_client_factory):
    c, calls = recording_client_factory(_warn_spec())
    r = c.post(
        URL,
        json=award_body(has_override=True, override_justification="Renewal in hand"),
    )
    assert r.status_code == 201
    params = calls["rpc"]["fn_create_award"]
    assert params["p_has_override"] is True
    assert params["p_override_justification"] == "Renewal in hand"
    assert params["p_validation_results"]["has_warnings"] is True


# ── block → 422 (non-overridable), no write ──────────────────────────────


def test_block_superseded_returns_422(recording_client_factory):
    c, calls = recording_client_factory(clean_spec(is_superseded=True))
    r = c.post(URL, json=award_body(has_override=True, override_justification="x"))
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["has_blocking"] is True
    assert detail["can_award"] is False
    elig = next(c for c in detail["checks"] if c["check"] == "submission_eligibility")
    assert elig["severity"] == "block"
    # Block short-circuits before any write — the RPC is never called.
    assert "rpc" not in calls


def test_block_draft_returns_422(client_factory):
    c = client_factory(clean_spec(is_draft=True))
    r = c.post(URL, json=award_body())
    assert r.status_code == 422
    assert r.json()["detail"]["has_blocking"] is True


def test_block_wrong_status_returns_422(client_factory):
    c = client_factory(clean_spec(status="rejected"))
    r = c.post(URL, json=award_body())
    assert r.status_code == 422
    assert r.json()["detail"]["has_blocking"] is True


def test_block_expired_insurance_returns_422(client_factory):
    c = client_factory(clean_spec(insurance_expiration="2000-01-01"))
    r = c.post(URL, json=award_body())
    assert r.status_code == 422
    detail = r.json()["detail"]
    ins = next(c for c in detail["checks"] if c["check"] == "insurance_validity")
    assert ins["severity"] == "block"


# ── Structural preconditions ─────────────────────────────────────────────


def test_submission_not_found_returns_404(client_factory):
    c = client_factory({"bid_submissions": {"select": []}})
    r = c.post(URL, json=award_body())
    assert r.status_code == 404


def test_open_package_returns_422_precondition(recording_client_factory):
    c, calls = recording_client_factory(clean_spec(package_status="open"))
    r = c.post(URL, json=award_body())
    assert r.status_code == 422
    # Precondition message is a plain string, not the validation result.
    assert isinstance(r.json()["detail"], str)
    assert "rpc" not in calls


def test_cancelled_package_returns_422_precondition(client_factory):
    c = client_factory(clean_spec(package_status="cancelled"))
    r = c.post(URL, json=award_body())
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


def test_pending_revision_blocks_award_409(client_factory):
    """A pending revision request on the package blocks award-create with 409."""
    spec = clean_spec()
    # Any row returned for bid_revision_requests means a pending revision exists
    # (the service filters .eq("status","pending"); the mock returns this verbatim).
    spec["bid_revision_requests"] = {"select": [{"id": str(uuid4())}]}
    c = client_factory(spec)
    r = c.post(URL, json=award_body())
    assert r.status_code == 409
    assert "revision" in r.json()["detail"].lower()


def test_no_pending_revision_allows_award(recording_client_factory):
    """No pending revision (empty result) → award proceeds normally."""
    spec = clean_spec()
    spec["bid_revision_requests"] = {"select": []}
    c, calls = recording_client_factory(spec)
    r = c.post(URL, json=award_body())
    assert r.status_code == 201
    assert "fn_create_award" in calls["rpc"]
    assert r.json()["status"] == "pending_acceptance"


def test_second_active_award_returns_clean_409(client_factory):
    spec = clean_spec()
    # The unique-index 23505 now surfaces through the RPC, not a table insert.
    spec["rpc"] = {
        "fn_create_award": APIError(
            {"code": "23505", "message": "duplicate key value violates unique constraint"}
        )
    }
    c = client_factory(spec)
    r = c.post(URL, json=award_body())
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)
