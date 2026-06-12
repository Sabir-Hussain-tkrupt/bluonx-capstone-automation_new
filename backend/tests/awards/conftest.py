"""
Shared fixtures for award endpoint tests.

Covers the Task 9.2 award-create write path + validation override gate. The
`make_db` mock keys canned data by table + op (select/insert/update); the
`*_recording` variant additionally captures write payloads so tests can assert
the *server-derived* award row (has_override, snapshot, amount). PM auth pattern
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


def make_db_recording(spec: dict, calls: dict) -> MagicMock:
    """Like make_db, but records the first positional arg of every
    select/insert/update/delete call into ``calls[table][op]`` so a test can
    assert exactly what the service wrote (e.g. the server-derived award row)."""
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


@pytest.fixture()
def recording_client_factory(authed_user):
    """Returns (TestClient, calls_dict). `calls_dict[table][op]` lists the
    payloads the service passed to that write — for asserting the server-derived
    award row and the tasks status update."""

    def _make(spec: dict):
        calls: dict = {}
        app.dependency_overrides[get_current_active_user] = lambda: authed_user
        app.dependency_overrides[get_supabase] = lambda: make_db_recording(spec, calls)
        return TestClient(app), calls

    yield _make
    app.dependency_overrides.clear()


def award_body(**overrides) -> dict:
    """Task 9.2 request payload — only the submission + (optional) override
    fields. task_id / vendor_id / award_amount are server-derived, never sent."""
    body: dict = {"bid_submission_id": str(SUBMISSION_ID)}
    body.update(overrides)
    return body
