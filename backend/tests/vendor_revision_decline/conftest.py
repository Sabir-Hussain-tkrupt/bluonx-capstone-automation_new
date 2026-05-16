"""
Fixtures for the vendor revision-decline click-through (B.5).

Self-contained op-aware Supabase mock (same shape as the
bid_revision_requests suite) so this package has no cross-package import.
No auth override — the endpoint takes a raw token in the URL, not a JWT.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.supabase_client import get_supabase
from app.main import app

REVISION_REQUEST_ID = uuid4()
INVITATION_ID = uuid4()
RAW_TOKEN = "vendor-decline-raw-token"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


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
        for m in (
            "eq", "neq", "in_", "is_", "order", "limit",
            "single", "maybe_single",
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
def client_factory():
    def _make(spec: dict):
        app.dependency_overrides[get_supabase] = lambda: make_db(spec)
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()
