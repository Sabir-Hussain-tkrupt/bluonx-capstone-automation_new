"""
Shared fixtures for the cross-project bid package list view (Task 6.2).

The service issues a single PostgREST request with aliased embeds:

    db.table("bid_packages")
      .select(
          "id, task_id, round_number, deadline, status, created_at, "
          "tasks!inner(id, name, project_id, projects!inner(id, name)), "
          "all_invitations:bid_invitations(count), "
          "submitted_invitations:bid_invitations(count)"
      )
      .eq("submitted_invitations.status", "submitted")
      [.eq(...) | .order(...)]
      .execute()

Each row returns the embedded `tasks`, `tasks.projects`, `all_invitations`
(list of `{count}`), and `submitted_invitations` (list of `{count}`). The
service flattens these into the `BidPackageListItem` shape.

All Supabase operations are mocked via MagicMock chains.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


# ── Deterministic IDs ──────────────────────────────────────────────────────

PROJECT_A_ID = uuid4()
PROJECT_B_ID = uuid4()

TASK_A_ID = uuid4()
TASK_B_ID = uuid4()
TASK_C_ID = uuid4()

PACKAGE_OPEN_ID = uuid4()
PACKAGE_EVALUATING_ID = uuid4()
PACKAGE_CLOSED_ID = uuid4()


# ── Sample row builder ─────────────────────────────────────────────────────


def _make_row(
    *,
    id_,
    task_id,
    task_name,
    project_id,
    project_name,
    round_number=1,
    deadline_offset_days=14,
    status="open",
    total_invitations=4,
    submitted_count=1,
    created_at_offset_days=0,
) -> dict:
    """Build a row mimicking the PostgREST aliased-embed response shape."""
    now = datetime.now(timezone.utc)
    deadline = (now + timedelta(days=deadline_offset_days)).isoformat()
    created_at = (now - timedelta(days=created_at_offset_days)).isoformat()
    return {
        "id": str(id_),
        "task_id": str(task_id),
        "round_number": round_number,
        "deadline": deadline,
        "status": status,
        "created_at": created_at,
        "tasks": {
            "id": str(task_id),
            "name": task_name,
            "project_id": str(project_id),
            "projects": {"id": str(project_id), "name": project_name},
        },
        "all_invitations": [{"count": total_invitations}],
        "submitted_invitations": [{"count": submitted_count}],
    }


@pytest.fixture()
def sample_rows() -> list[dict]:
    """Three packages spanning two projects and three statuses."""
    return [
        _make_row(
            id_=PACKAGE_OPEN_ID,
            task_id=TASK_A_ID,
            task_name="Rough Grading",
            project_id=PROJECT_A_ID,
            project_name="Alpine Estates",
            round_number=1,
            deadline_offset_days=10,
            status="open",
            total_invitations=5,
            submitted_count=2,
            created_at_offset_days=2,
        ),
        _make_row(
            id_=PACKAGE_EVALUATING_ID,
            task_id=TASK_B_ID,
            task_name="Storm Drainage",
            project_id=PROJECT_A_ID,
            project_name="Alpine Estates",
            round_number=2,
            deadline_offset_days=3,
            status="evaluating",
            total_invitations=4,
            submitted_count=4,
            created_at_offset_days=12,
        ),
        _make_row(
            id_=PACKAGE_CLOSED_ID,
            task_id=TASK_C_ID,
            task_name="Site Survey",
            project_id=PROJECT_B_ID,
            project_name="Birch Park",
            round_number=1,
            deadline_offset_days=-1,
            status="closed",
            total_invitations=3,
            submitted_count=3,
            created_at_offset_days=20,
        ),
    ]


# ── Mock chain builder ─────────────────────────────────────────────────────


def build_chain(data=None):
    """Mock chain that accepts the full PostgREST builder API and returns
    `data` from .execute().
    """
    chain = MagicMock()
    result = MagicMock()
    result.data = data if data is not None else []

    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.in_.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = result
    return chain


@pytest.fixture()
def mock_supabase(sample_rows) -> MagicMock:
    """Default mock — `db.table("bid_packages")` returns `sample_rows`."""
    client = MagicMock()

    def table_side_effect(name: str):
        if name == "bid_packages":
            return build_chain(data=sample_rows)
        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    return client


@pytest.fixture()
def mock_supabase_empty() -> MagicMock:
    client = MagicMock()
    client.table.side_effect = lambda _name: build_chain(data=[])
    return client
