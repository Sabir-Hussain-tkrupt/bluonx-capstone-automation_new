"""Shared fixtures for vendor-performance-review tests.

`make_db_recording(spec, calls)` records write payloads so a test can assert the
server-resolved vendor_id actually written (never the client's). Table data is
keyed by table + op; an Exception value is raised from `.execute()` to inject a
23505 unique violation.
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
CONTRACT_VENDOR_ID = uuid4()   # the contract's real vendor (what must be written)
CLIENT_VENDOR_ID = uuid4()     # a value the client might try to sneak in
REVIEW_ID = uuid4()


def make_db_recording(spec: dict, calls: dict) -> MagicMock:
    client = MagicMock()

    def _table(name: str):
        tspec = spec.get(name, {})
        chain = MagicMock()
        state = {"op": "select"}

        def _setop(op):
            def _f(*a, **_k):
                state["op"] = op
                if a:
                    calls.setdefault(name, {}).setdefault(op, []).append(a[0])
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

    client.table.side_effect = _table
    return client


def make_contract_row(*, status: str = "completed") -> dict:
    return {
        "id": str(CONTRACT_ID),
        "status": status,
        "vendor_id": str(CONTRACT_VENDOR_ID),
    }


def make_review_row(*, rating: int = 4, vendor_id=CONTRACT_VENDOR_ID) -> dict:
    return {
        "id": str(REVIEW_ID),
        "contract_id": str(CONTRACT_ID),
        "vendor_id": str(vendor_id),
        "rating": rating,
        "notes": None,
        "reviewed_by": str(PM_USER_ID),
        "reviewed_at": "2026-07-17T00:00:00+00:00",
        "created_at": "2026-07-17T00:00:00+00:00",
        "updated_at": "2026-07-17T00:00:00+00:00",
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
def recording_client_factory(authed_user):
    def _make(spec: dict):
        calls: dict = {}
        app.dependency_overrides[get_current_active_user] = lambda: authed_user
        app.dependency_overrides[get_supabase] = lambda: make_db_recording(spec, calls)
        return TestClient(app), calls

    yield _make
    app.dependency_overrides.clear()
