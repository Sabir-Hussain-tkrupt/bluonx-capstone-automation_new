"""
Shared fixtures for per-vendor bid revision Step-2 tests.

Provides an op-aware Supabase mock: db.table(name).<op>()....execute()
returns data keyed by (table, op) so a single flow can hit the same table
for both a SELECT and an INSERT/UPDATE and get different rows back. A spec
value that is an Exception is raised from .execute() (used for the
unique-violation path).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

# ── Deterministic IDs ──────────────────────────────────────────────────────

INVITATION_ID = uuid4()
BID_PACKAGE_ID = uuid4()
TASK_ID = uuid4()
VENDOR_ID = uuid4()
ORIGINAL_SUBMISSION_ID = uuid4()
REVISION_REQUEST_ID = uuid4()
PM_USER_ID = uuid4()

FIXED_RAW_TOKEN = "fixed-raw-token-for-tests"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def revision_row(**overrides) -> dict:
    """A full bid_revision_requests row (all response columns)."""
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(REVISION_REQUEST_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "original_submission_id": str(ORIGINAL_SUBMISSION_ID),
        "pm_note": "Please re-price line 3.",
        "revision_deadline": _future(),
        "status": "pending",
        "decline_reason": None,
        "requested_by": str(PM_USER_ID),
        "requested_at": now,
        "responded_at": None,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


def token_row(**overrides) -> dict:
    row = {
        "id": str(uuid4()),
        "bid_invitation_id": str(INVITATION_ID),
        "expires_at": _future(),
        "revoked_at": None,
        "bid_revision_request_id": str(REVISION_REQUEST_ID),
    }
    row.update(overrides)
    return row


# ── Op-aware Supabase mock ─────────────────────────────────────────────────


def make_db(spec: dict) -> MagicMock:
    """spec = {table: {"select": data|Exc, "insert": ..., "update": ...,
    "default": ...}}."""
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
        for m in (
            "eq", "neq", "in_", "is_", "order", "limit",
            "single", "maybe_single", "gt", "lt", "gte", "lte",
        ):
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
    """Returns make_client(spec, *, auth=True) → TestClient."""
    created: list = []

    def _make(spec: dict, *, auth: bool = True):
        if auth:
            app.dependency_overrides[get_current_active_user] = lambda: authed_user
        app.dependency_overrides[get_supabase] = lambda: make_db(spec)
        c = TestClient(app)
        created.append(c)
        return c

    yield _make
    app.dependency_overrides.clear()
