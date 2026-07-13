"""Mocked-Supabase endpoint tests for milestone writes (Phase 10 foundation).

Exercises the contract gate, sort_order/contract_id resolution, the RPC-backed
transitions (via a faithful FakeDB mirror of transition_milestone), the PATCH
date-lock, the delete activity guard, and PT-SQLSTATE → HTTP mapping through the
FastAPI router. The RPC's own invariants (cycle bump, immutable ledger row,
baseline untouched) are covered in the integration suite.
"""

from __future__ import annotations

from postgrest.exceptions import APIError

from .conftest import (
    CONTRACT_ID,
    MILESTONE_ID,
    PM_USER_ID,
    TASK_ID,
    FakeDB,
    make_client,
    milestone_row,
)

BASE = "/api/v1/milestones"


def _create_body(**overrides) -> dict:
    body = {
        "task_id": str(TASK_ID),
        "name": "Foundation Pour",
        "start_date": "2026-08-01",
        "end_date": "2026-08-15",
        "notes": None,
    }
    body.update(overrides)
    return body


# ── create: contract gate + fn_create_milestone ──────────────────────────


def test_create_blocked_without_active_contract(authed_user):
    db = FakeDB(contract_row=None)
    client = make_client(db, authed_user)
    resp = client.post(BASE, json=_create_body())
    assert resp.status_code == 422
    assert "active contract" in resp.json()["detail"].lower()
    assert db.last_rpc is None


def test_create_routes_through_rpc_with_resolved_fields(authed_user):
    db = FakeDB(contract_row={"id": str(CONTRACT_ID)}, existing_orders=[0, 1])
    client = make_client(db, authed_user)
    resp = client.post(BASE, json=_create_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["contract_id"] == str(CONTRACT_ID)
    assert body["status"] == "scheduled"
    assert db.last_rpc["name"] == "fn_create_milestone"
    params = db.last_rpc["params"]
    # sort_order appended after the existing max (1) → 2
    assert params["p_sort_order"] == 2
    assert params["p_created_by"] == authed_user["user_id"]
    assert params["p_contract_id"] == str(CONTRACT_ID)


def test_create_first_milestone_sort_order_zero(authed_user):
    db = FakeDB(contract_row={"id": str(CONTRACT_ID)}, existing_orders=[])
    client = make_client(db, authed_user)
    resp = client.post(BASE, json=_create_body())
    assert resp.status_code == 201
    assert db.last_rpc["params"]["p_sort_order"] == 0


def test_create_rejects_end_before_start(authed_user):
    db = FakeDB(contract_row={"id": str(CONTRACT_ID)})
    client = make_client(db, authed_user)
    resp = client.post(BASE, json=_create_body(start_date="2026-08-15", end_date="2026-08-01"))
    assert resp.status_code == 422
    assert "before" in resp.json()["detail"].lower()
    assert db.last_rpc is None


# ── update: mutable fields + date lock ────────────────────────────────────


def test_update_patches_name(authed_user):
    db = FakeDB(current_milestone=milestone_row())
    client = make_client(db, authed_user)
    resp = client.patch(f"{BASE}/{MILESTONE_ID}", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert db.last_update == {"name": "Renamed"}


def test_update_404_when_missing(authed_user):
    db = FakeDB(milestone_missing=True)
    client = make_client(db, authed_user)
    resp = client.patch(f"{BASE}/{MILESTONE_ID}", json={"name": "X"})
    assert resp.status_code == 404


def test_update_date_edit_on_scheduled_milestone_succeeds(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="scheduled"))
    client = make_client(db, authed_user)
    resp = client.patch(f"{BASE}/{MILESTONE_ID}", json={"end_date": "2026-08-20"})
    assert resp.status_code == 200
    assert db.last_update["end_date"] == "2026-08-20"


def test_update_date_edit_blocked_when_live(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="in_progress"))
    client = make_client(db, authed_user)
    resp = client.patch(f"{BASE}/{MILESTONE_ID}", json={"end_date": "2026-08-20"})
    assert resp.status_code == 409
    assert "reschedule" in resp.json()["detail"].lower()
    assert db.last_update is None


def test_update_date_edit_blocked_when_alerts_exist(authed_user):
    # Still 'scheduled' but a check-in alert was sent → dates locked.
    db = FakeDB(current_milestone=milestone_row(status="scheduled"), has_alerts=True)
    client = make_client(db, authed_user)
    resp = client.patch(f"{BASE}/{MILESTONE_ID}", json={"end_date": "2026-08-20"})
    assert resp.status_code == 409
    assert db.last_update is None


def test_update_rejects_inverted_window(authed_user):
    # Existing start 2026-08-01; pushing end before it must 422 (still scheduled).
    db = FakeDB(current_milestone=milestone_row(status="scheduled", start_date="2026-08-01"))
    client = make_client(db, authed_user)
    resp = client.patch(f"{BASE}/{MILESTONE_ID}", json={"end_date": "2026-07-01"})
    assert resp.status_code == 422


# ── transitions (RPC-backed) ──────────────────────────────────────────────


def test_mark_started_from_scheduled(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="scheduled"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/mark-started", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
    params = db.last_rpc["params"]
    assert params["p_action"] == "pm_mark_started"
    assert params["p_actor_user_id"] == str(PM_USER_ID)
    assert params["p_actual_start_date"] is not None  # defaulted to today
    assert "actual start" in params["p_note"].lower()


def test_mark_started_blocked_when_already_in_progress(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="in_progress"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/mark-started", json={})
    assert resp.status_code == 409


def test_mark_completed_from_in_progress(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="in_progress"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/mark-completed", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert db.last_rpc["params"]["p_action"] == "pm_mark_completed"


def test_mark_completed_from_scheduled_allowed_without_start(authed_user):
    # Recording already-finished work: allowed, and no actual_start is invented.
    db = FakeDB(current_milestone=milestone_row(status="scheduled"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/mark-completed", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert db.last_rpc["params"]["p_actual_start_date"] is None


def test_mark_completed_blocked_from_completed(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="completed"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/mark-completed", json={})
    assert resp.status_code == 409


def test_mark_completed_rejects_end_before_actual_start(authed_user):
    db = FakeDB(
        current_milestone=milestone_row(status="in_progress", actual_start_date="2026-08-05")
    )
    client = make_client(db, authed_user)
    resp = client.post(
        f"{BASE}/{MILESTONE_ID}/mark-completed", json={"actual_end_date": "2026-08-01"}
    )
    assert resp.status_code == 422


def test_reschedule_from_delayed(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="delayed"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/reschedule", json={"end_date": "2026-09-30"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["end_date"] == "2026-09-30"
    params = db.last_rpc["params"]
    assert params["p_action"] == "pm_reschedule"
    assert params["p_new_end_date"] == "2026-09-30"


def test_reschedule_blocked_from_scheduled(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="scheduled"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/reschedule", json={"end_date": "2026-09-30"})
    assert resp.status_code == 409


def test_reschedule_blocked_from_completed(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="completed"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/reschedule", json={"end_date": "2026-09-30"})
    assert resp.status_code == 409


# ── cancel ────────────────────────────────────────────────────────────────


def test_cancel_from_in_progress(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="in_progress"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    params = db.last_rpc["params"]
    assert params["p_action"] == "pm_cancel"
    assert params["p_note"] == "Cancelled by PM"


def test_cancel_blocked_from_completed(authed_user):
    db = FakeDB(current_milestone=milestone_row(status="completed"))
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/cancel")
    assert resp.status_code == 409


# ── PT-SQLSTATE → HTTP mapping ─────────────────────────────────────────────


def test_transition_pt404_maps_to_404(authed_user):
    db = FakeDB(
        current_milestone=milestone_row(status="scheduled"),
        rpc_error=APIError({"code": "PT404", "message": "Milestone not found"}),
    )
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/mark-started", json={})
    assert resp.status_code == 404


def test_transition_pt422_maps_to_422(authed_user):
    db = FakeDB(
        current_milestone=milestone_row(status="scheduled"),
        rpc_error=APIError({"code": "PT422", "message": "bad dates"}),
    )
    client = make_client(db, authed_user)
    resp = client.post(f"{BASE}/{MILESTONE_ID}/mark-started", json={})
    assert resp.status_code == 422


# ── delete ────────────────────────────────────────────────────────────────


def test_delete_ok(authed_user):
    db = FakeDB(current_milestone=milestone_row())
    client = make_client(db, authed_user)
    resp = client.delete(f"{BASE}/{MILESTONE_ID}")
    assert resp.status_code == 204
    assert db.deleted is True


def test_delete_blocked_when_responses_exist(authed_user):
    db = FakeDB(current_milestone=milestone_row(), has_responses=True)
    client = make_client(db, authed_user)
    resp = client.delete(f"{BASE}/{MILESTONE_ID}")
    assert resp.status_code == 409
    assert "cancel it instead" in resp.json()["detail"].lower()
    assert db.deleted is False


def test_delete_blocked_when_alerts_exist(authed_user):
    db = FakeDB(current_milestone=milestone_row(), has_alerts=True)
    client = make_client(db, authed_user)
    resp = client.delete(f"{BASE}/{MILESTONE_ID}")
    assert resp.status_code == 409
    assert db.deleted is False


def test_delete_409_on_fk_violation(authed_user):
    db = FakeDB(current_milestone=milestone_row(), delete_fk_violation=True)
    client = make_client(db, authed_user)
    resp = client.delete(f"{BASE}/{MILESTONE_ID}")
    assert resp.status_code == 409
    assert "cancel it instead" in resp.json()["detail"].lower()
