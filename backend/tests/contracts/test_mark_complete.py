"""Tests for the mark-contract-complete write path.

Covers the service SQLSTATE→HTTP mapping (PT404→404, PT409→409) plus the endpoint
wiring. The gate itself lives inside fn_mark_contract_complete (row-locked); here we
only assert the service surfaces its raised SQLSTATE as a clean error and returns the
completed contract on success.
"""

from __future__ import annotations

import pytest
from postgrest.exceptions import APIError

from app.services import contract_service
from app.services.contract_service import ContractError

from .conftest import CONTRACT_ID, make_contract, make_db


# ── Service: success ─────────────────────────────────────────────────────


def test_mark_completed_returns_completed_contract():
    completed = make_contract(status="completed")
    db = make_db({"rpc": {"fn_mark_contract_complete": [completed]}})
    row = contract_service.mark_contract_completed(str(CONTRACT_ID), db=db)
    assert row["status"] == "completed"
    db.rpc.assert_called_once_with(
        "fn_mark_contract_complete", {"p_contract_id": str(CONTRACT_ID)}
    )


# ── Service: SQLSTATE mapping ────────────────────────────────────────────


def test_pt409_open_milestone_maps_to_409():
    err = APIError({"code": "PT409", "message": "Contract has 2 milestone(s) still open"})
    db = make_db({"rpc": {"fn_mark_contract_complete": err}})
    with pytest.raises(ContractError) as exc:
        contract_service.mark_contract_completed(str(CONTRACT_ID), db=db)
    assert exc.value.status_code == 409


def test_pt409_already_complete_maps_to_409():
    err = APIError({"code": "PT409", "message": "Contract is already complete"})
    db = make_db({"rpc": {"fn_mark_contract_complete": err}})
    with pytest.raises(ContractError) as exc:
        contract_service.mark_contract_completed(str(CONTRACT_ID), db=db)
    assert exc.value.status_code == 409


def test_pt404_maps_to_404():
    err = APIError({"code": "PT404", "message": "Contract not found"})
    db = make_db({"rpc": {"fn_mark_contract_complete": err}})
    with pytest.raises(ContractError) as exc:
        contract_service.mark_contract_completed(str(CONTRACT_ID), db=db)
    assert exc.value.status_code == 404


def test_unexpected_error_maps_to_502():
    err = APIError({"code": "42501", "message": "permission denied"})
    db = make_db({"rpc": {"fn_mark_contract_complete": err}})
    with pytest.raises(ContractError) as exc:
        contract_service.mark_contract_completed(str(CONTRACT_ID), db=db)
    assert exc.value.status_code == 502


def test_empty_rpc_result_maps_to_500():
    db = make_db({"rpc": {"fn_mark_contract_complete": []}})
    with pytest.raises(ContractError) as exc:
        contract_service.mark_contract_completed(str(CONTRACT_ID), db=db)
    assert exc.value.status_code == 500


# ── Endpoint wiring ──────────────────────────────────────────────────────


def test_endpoint_success_returns_200(client_factory):
    completed = make_contract(status="completed")
    client, _ = client_factory({"rpc": {"fn_mark_contract_complete": [completed]}})
    resp = client.post(f"/api/v1/contracts/{CONTRACT_ID}/mark-complete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_endpoint_open_milestone_returns_409(client_factory):
    err = APIError({"code": "PT409", "message": "milestone(s) still open"})
    client, _ = client_factory({"rpc": {"fn_mark_contract_complete": err}})
    resp = client.post(f"/api/v1/contracts/{CONTRACT_ID}/mark-complete")
    assert resp.status_code == 409
