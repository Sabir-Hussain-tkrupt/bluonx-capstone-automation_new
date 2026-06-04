"""Task 8.1.5 — GET /v1/bid-packages/{id} returns desired_start_date.

Locks the service-layer dict shape so the field can't be silently
dropped on its way from the bid_packages row to the PM detail page.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.invitation_tracking_service import get_bid_package_detail

from .conftest import DESIRED_START_ISO


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()


def _build_chain(data):
    chain = MagicMock()
    result = MagicMock()
    result.data = data
    for m in (
        "select", "insert", "update", "delete",
        "eq", "neq", "in_", "is_", "order", "limit",
        "single", "maybe_single",
    ):
        getattr(chain, m).return_value = chain
    chain.execute.return_value = result
    return chain


def _db_with_package(desired_start_date) -> MagicMock:
    pkg_id = str(uuid4())
    task_id = str(uuid4())
    pkg_row = {
        "id": pkg_id,
        "task_id": task_id,
        "round_number": 1,
        "deadline": _future(),
        "status": "open",
        "instructions": None,
        "desired_start_date": desired_start_date,
        "tasks": {"name": "Mass Grading"},
        "bid_templates": {
            "id": str(uuid4()),
            "name": "Standard",
            "is_lump_sum": True,
        },
    }
    db = MagicMock()

    def _table(name):
        if name == "bid_packages":
            return _build_chain(pkg_row)
        # invitations / documents / awards / submitted bids: all empty
        return _build_chain([])

    db.table.side_effect = _table
    return db, pkg_id


@pytest.mark.asyncio
async def test_returns_desired_start_date_when_present():
    db, pkg_id = _db_with_package(DESIRED_START_ISO)
    result = await get_bid_package_detail(bid_package_id=pkg_id, db=db)
    assert result["desired_start_date"] == DESIRED_START_ISO


@pytest.mark.asyncio
async def test_returns_null_when_package_has_no_desired_date():
    db, pkg_id = _db_with_package(None)
    result = await get_bid_package_detail(bid_package_id=pkg_id, db=db)
    assert result["desired_start_date"] is None
