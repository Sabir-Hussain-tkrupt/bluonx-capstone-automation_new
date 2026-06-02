"""
Unit tests for the in-use detection helpers in app.routers.bid_templates.

Freeze rule (Task 8.1 CFT):
    A template is "in use" iff any bid_packages row references it AND
    that row's status is NOT 'cancelled'.

bid_packages.status enum: open | closed | evaluating | cancelled
(no 'draft' status; verified in database/bluonx_complete_schema.sql).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.routers.bid_templates import (
    _all_referencing_packages,
    _is_template_in_use,
    _referencing_live_packages,
)

from .conftest import (
    TEMPLATE_ID,
    package_cancelled as _pkg_cancelled,  # noqa: F401 (re-imported for fixture access)
)


def _shaped(row: dict) -> dict:
    """The shape the helper is expected to return (flattened task_name)."""
    return {
        "id": row["id"],
        "status": row["status"],
        "task_name": row["tasks"]["name"],
    }


@pytest.mark.parametrize(
    "live_status",
    ["open", "closed", "evaluating"],
)
def test_helper_returns_row_for_each_live_status(live_status, sample_trade):
    """Every non-cancelled status counts as a live reference."""
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "status": live_status,
        "task_id": "22222222-2222-2222-2222-222222222222",
        "tasks": {"name": "Sample Task"},
    }

    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.execute.return_value = MagicMock(data=[row])
    db.table.return_value = chain

    result = _referencing_live_packages(db, TEMPLATE_ID)

    assert result == [_shaped(row)]
    assert _is_template_in_use(db, TEMPLATE_ID) is True
    chain.neq.assert_called_with("status", "cancelled")


def test_helper_returns_empty_when_only_cancelled(package_cancelled):
    """A cancelled-only reference is editable; live query returns [].

    The mock simulates the DB-side filter: when the router calls
    `.neq("status","cancelled")`, the DB returns 0 rows.
    """
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    db.table.return_value = chain

    assert _referencing_live_packages(db, TEMPLATE_ID) == []
    assert _is_template_in_use(db, TEMPLATE_ID) is False


def test_helper_returns_empty_when_no_refs_at_all():
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    db.table.return_value = chain

    assert _referencing_live_packages(db, TEMPLATE_ID) == []
    assert _is_template_in_use(db, TEMPLATE_ID) is False


def test_helper_returns_only_live_in_mixed_state(package_open, package_cancelled):
    """When the DB has open + cancelled, the .neq filter strips cancelled."""
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    # Simulated DB-side filter: only the open row survives .neq
    chain.execute.return_value = MagicMock(data=[package_open])
    db.table.return_value = chain

    result = _referencing_live_packages(db, TEMPLATE_ID)
    assert result == [_shaped(package_open)]
    assert _is_template_in_use(db, TEMPLATE_ID) is True


def test_all_referencing_includes_cancelled(package_open, package_cancelled):
    """The all-refs helper (used by the delete message) does NOT filter by status."""
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.execute.return_value = MagicMock(data=[package_open, package_cancelled])
    db.table.return_value = chain

    result = _all_referencing_packages(db, TEMPLATE_ID)

    assert _shaped(package_open) in result
    assert _shaped(package_cancelled) in result
    # No status filter expected
    chain.neq.assert_not_called()
