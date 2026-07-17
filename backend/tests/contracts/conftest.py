"""Shared fixtures for contract mark-complete tests.

`make_db(spec)` is the per-table + rpc mock used across the suite (mirrors
tests/awards/conftest.py): canned data keyed by table + op, RPC results keyed by
name under spec["rpc"], and an Exception value is raised from `.execute()` so a
test can inject an APIError with a PT SQLSTATE.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

PM_USER_ID = uuid4()
CONTRACT_ID = uuid4()
VENDOR_ID = uuid4()


def make_db(spec: dict) -> MagicMock:
    client = MagicMock()

    def _table(name: str):
        tspec = spec.get(name, {})
        chain = MagicMock()
        state = {"op": "select"}

        def _setop(op):
            def _f(*_a, **_k):
                state["op"] = op
                return chain

            return _f

        for op in ("select", "insert", "update", "delete", "upsert"):
            getattr(chain, op).side_effect = _setop(op)
        for m in ("eq", "neq", "in_", "is_", "order", "limit", "single", "maybe_single"):
            getattr(chain, m).return_value = chain

        def _execute(*_a, **_k):
            data = tspec.get(state["op"], tspec.get("default", []))
            if isinstance(data, Exception):
                raise data
            res = MagicMock()
            res.data = data
            return res

        chain.execute.side_effect = _execute
        return chain

    def _rpc(name: str, params=None, *_a, **_k):
        chain = MagicMock()

        def _execute(*_ea, **_ek):
            data = spec.get("rpc", {}).get(name, [])
            if isinstance(data, Exception):
                raise data
            res = MagicMock()
            res.data = data
            return res

        chain.execute.side_effect = _execute
        return chain

    client.table.side_effect = _table
    client.rpc.side_effect = _rpc
    return client


def make_contract(*, status: str = "executed", contract_id=CONTRACT_ID) -> dict:
    return {
        "id": str(contract_id),
        "award_id": str(uuid4()),
        "vendor_id": str(VENDOR_ID),
        "task_id": str(uuid4()),
        "contract_number": "CON-2026-ABCD1234",
        "start_date": None,
        "end_date": None,
        "contract_amount": "100000.00",
        "payment_terms": None,
        "status": status,
        "signed_at": None,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:00:00+00:00",
    }


@pytest.fixture()
def authed_user() -> dict:
    return {
        "user_id": str(PM_USER_ID),
        "email": "pm@example.com",
        "full_name": "PM User",
        "role": "project_manager",
        "is_active": True,
    }


@pytest.fixture()
def client_factory(authed_user):
    def _make(spec: dict):
        db = make_db(spec)
        app.dependency_overrides[get_current_active_user] = lambda: authed_user
        app.dependency_overrides[get_supabase] = lambda: db
        return TestClient(app), db

    yield _make
    app.dependency_overrides.clear()
