"""
Shared fixtures for Task 8.2 weighted scoring engine tests.

`make_db(spec)` mirrors backend/tests/awards/conftest.py — per-table,
per-operation mock data. Adds upsert support since the scoring engine is the
first caller of `.upsert()` in the codebase.

Data shapes match what real PostgREST returns: dates / timestamptz as ISO
strings, DECIMAL as strings, nested joins as nested dicts.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app


# ── Deterministic IDs ────────────────────────────────────────────────────

PM_USER_ID = uuid4()
TASK_ID = uuid4()
BID_PACKAGE_ID = uuid4()
VENDOR_IDS = [uuid4() for _ in range(3)]
SUBMISSION_IDS = [uuid4() for _ in range(3)]
INVITATION_IDS = [uuid4() for _ in range(3)]
SCORE_ROW_IDS = [uuid4() for _ in range(3)]

# A real ID that the mocked DB will deliberately not return on lookup.
UNKNOWN_BID_PACKAGE_ID = uuid4()


# ── Reference dates ──────────────────────────────────────────────────────

PACKAGE_DEADLINE = datetime(2026, 7, 1, 17, 0, 0, tzinfo=timezone.utc)
PACKAGE_DESIRED_START = date(2026, 7, 15)


# ── Mock Supabase client ─────────────────────────────────────────────────


def make_db(spec: dict) -> MagicMock:
    """
    Build a per-table, per-operation Supabase mock.

    spec shape:
        {
          "bid_packages": {"select": <data>, "default": [...]},
          "bid_scores":   {"select": [...], "upsert": [...]},
          ...
        }
    `<data>` may be a dict (single-row response), a list (multi-row response),
    or an Exception to raise from `.execute()`.
    """
    client = MagicMock()
    call_log: list[tuple[str, str, tuple, dict]] = []
    client._call_log = call_log
    client._chains: dict[str, MagicMock] = {}

    def _table(name: str):
        if name in client._chains:
            return client._chains[name]

        tspec = spec.get(name, {})
        chain = MagicMock()
        client._chains[name] = chain
        state = {"op": "select", "args": (), "kwargs": {}}

        def _setop(op):
            def _f(*args, **kwargs):
                state["op"] = op
                state["args"] = args
                state["kwargs"] = kwargs
                call_log.append((name, op, args, kwargs))
                return chain

            return _f

        for op in ("select", "insert", "update", "delete", "upsert"):
            getattr(chain, op).side_effect = _setop(op)

        for m in (
            "eq", "neq", "in_", "is_", "not_", "gt", "gte", "lt", "lte",
            "order", "limit", "single", "maybe_single", "match",
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


# ── Sample-row factories ─────────────────────────────────────────────────


def make_package(
    *,
    bid_package_id: UUID = BID_PACKAGE_ID,
    task_id: UUID = TASK_ID,
    deadline: datetime = PACKAGE_DEADLINE,
    desired_start_date: date | None = PACKAGE_DESIRED_START,
    bid_type: str = "competitive",
) -> dict:
    return {
        "id": str(bid_package_id),
        "task_id": str(task_id),
        "deadline": deadline.isoformat(),
        "desired_start_date": (
            desired_start_date.isoformat() if desired_start_date else None
        ),
        "status": "open",
        "round_number": 1,
        "tasks": {"bid_type": bid_type, "id": str(task_id)},
    }


def make_vendor(
    *,
    onboarding_status: str = "complete",
    insurance_expiration_date: date | None = date(2026, 12, 31),
    max_active_jobs: int | None = 5,
    current_active_jobs: int = 1,
) -> dict:
    return {
        "onboarding_status": onboarding_status,
        "insurance_expiration_date": (
            insurance_expiration_date.isoformat()
            if insurance_expiration_date else None
        ),
        "max_active_jobs": max_active_jobs,
        "current_active_jobs": current_active_jobs,
    }


def make_submission(
    *,
    submission_id: UUID,
    vendor_id: UUID,
    bid_invitation_id: UUID,
    total_amount: str | None = "100000.00",
    proposed_start_date: date | None = date(2026, 7, 15),
    status: str = "submitted",
    is_superseded: bool = False,
    is_draft: bool = False,
    vendor: dict | None = None,
) -> dict:
    return {
        "id": str(submission_id),
        "vendor_id": str(vendor_id),
        "bid_invitation_id": str(bid_invitation_id),
        "total_amount": total_amount,
        "proposed_start_date": (
            proposed_start_date.isoformat() if proposed_start_date else None
        ),
        "status": status,
        "is_superseded": is_superseded,
        "is_draft": is_draft,
        "vendors": vendor or make_vendor(),
    }


def make_invitation(*, invitation_id: UUID, bid_package_id: UUID = BID_PACKAGE_ID) -> dict:
    return {"id": str(invitation_id), "bid_package_id": str(bid_package_id)}


def make_score_row(
    *,
    score_id: UUID,
    submission_id: UUID,
    scored_by: UUID | None = None,
    total_weighted_score: str = "82.50",
    scoring_metadata: dict | None = None,
) -> dict:
    return {
        "id": str(score_id),
        "bid_submission_id": str(submission_id),
        "price_score": "100.00",
        "compliance_score": "100.00",
        "performance_score": "75.00",
        "capacity_score": "80.00",
        "timeline_score": "75.00",
        "total_weighted_score": total_weighted_score,
        "scoring_metadata": scoring_metadata or {"rubric_version": "v1.0"},
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "scored_by": str(scored_by) if scored_by else None,
    }


# ── Auth / client overrides ──────────────────────────────────────────────


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
    """
    Build a TestClient with overridden auth + Supabase. Returns a callable
    `_make(spec)` that wires a fresh make_db(spec) into the FastAPI app.
    """
    def _make(spec: dict):
        db = make_db(spec)
        app.dependency_overrides[get_current_active_user] = lambda: authed_user
        app.dependency_overrides[get_supabase] = lambda: db
        return TestClient(app), db

    yield _make
    app.dependency_overrides.clear()
