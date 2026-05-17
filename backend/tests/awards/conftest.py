"""
Shared fixtures for award endpoint tests.

create_award is still a 501 stub; Step 3 adds only a fail-fast
is_superseded guard as the first executable statement. PM auth pattern
mirrors the bid_revision_requests suite.
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
TASK_ID = uuid4()
VENDOR_ID = uuid4()
SUBMISSION_ID = uuid4()


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

        chain.select.side_effect = _setop("select")
        chain.insert.side_effect = _setop("insert")
        chain.update.side_effect = _setop("update")
        chain.delete.side_effect = _setop("delete")
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
        app.dependency_overrides[get_current_active_user] = lambda: authed_user
        app.dependency_overrides[get_supabase] = lambda: make_db(spec)
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def award_body(**overrides) -> dict:
    body = {
        "task_id": str(TASK_ID),
        "bid_submission_id": str(SUBMISSION_ID),
        "vendor_id": str(VENDOR_ID),
        "award_amount": "50000.00",
        "has_override": False,
    }
    body.update(overrides)
    return body
