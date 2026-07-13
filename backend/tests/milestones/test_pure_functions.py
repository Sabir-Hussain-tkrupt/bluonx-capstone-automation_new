"""Pure-function tests for milestone_service (Phase 10 foundation) — no DB.

Transition legality now lives entirely in the transition_milestone() RPC (the
Python guard was removed), so the remaining pure validators are:
  - validate_date_order → 422 when end < start
  - next_sort_order     → max(existing, default=-1) + 1
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.milestone_service import (
    MilestoneError,
    next_sort_order,
    validate_date_order,
)


# ── validate_date_order ─────────────────────────────────────────────────


def test_date_order_end_after_start_ok():
    validate_date_order(date(2026, 7, 1), date(2026, 7, 10))  # no raise


def test_date_order_equal_ok():
    validate_date_order(date(2026, 7, 1), date(2026, 7, 1))  # same-day is allowed


def test_date_order_end_before_start_raises_422():
    with pytest.raises(MilestoneError) as exc:
        validate_date_order(date(2026, 7, 10), date(2026, 7, 1))
    assert exc.value.status_code == 422


# ── next_sort_order ──────────────────────────────────────────────────────


def test_next_sort_order_empty_is_zero():
    assert next_sort_order([]) == 0


def test_next_sort_order_appends_after_max():
    assert next_sort_order([0, 1, 2]) == 3


def test_next_sort_order_uses_max_not_count():
    assert next_sort_order([0, 5, 2]) == 6
