"""Pure-function tests for milestone_service (Phase 10.1) — no DB.

Targets the three extracted validators:
  - validate_date_order      → 422 when end < start
  - assert_transition_allowed → 409 on an illegal (current, action) pair
  - next_sort_order          → max(existing, default=-1) + 1

The status vocabulary is the migrated 6-status set:
  scheduled, in_progress, delayed, unresponsive, completed, cancelled

Actions funnel through _apply_status:
  start      → in_progress, allowed only from {scheduled}
  complete   → completed,   allowed from {scheduled, in_progress, delayed, unresponsive}
  reschedule → in_progress, allowed from {in_progress, delayed, unresponsive}
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.milestone_service import (
    MilestoneError,
    assert_transition_allowed,
    next_sort_order,
    validate_date_order,
)

ALL_STATUSES = [
    "scheduled", "in_progress", "delayed", "unresponsive", "completed", "cancelled",
]


# ── validate_date_order ─────────────────────────────────────────────────


def test_date_order_end_after_start_ok():
    validate_date_order(date(2026, 7, 1), date(2026, 7, 10))  # no raise


def test_date_order_equal_ok():
    validate_date_order(date(2026, 7, 1), date(2026, 7, 1))  # same-day is allowed


def test_date_order_end_before_start_raises_422():
    with pytest.raises(MilestoneError) as exc:
        validate_date_order(date(2026, 7, 10), date(2026, 7, 1))
    assert exc.value.status_code == 422


# ── assert_transition_allowed ────────────────────────────────────────────

_ALLOWED = {
    "start": {"scheduled"},
    "complete": {"scheduled", "in_progress", "delayed", "unresponsive"},
    "reschedule": {"in_progress", "delayed", "unresponsive"},
}


@pytest.mark.parametrize("action, allowed", _ALLOWED.items())
def test_allowed_transitions_pass(action, allowed):
    for current in allowed:
        assert_transition_allowed(current, action)  # no raise


@pytest.mark.parametrize("action, allowed", _ALLOWED.items())
def test_blocked_transitions_raise_409(action, allowed):
    for current in ALL_STATUSES:
        if current in allowed:
            continue
        with pytest.raises(MilestoneError) as exc:
            assert_transition_allowed(current, action)
        assert exc.value.status_code == 409


# ── next_sort_order ──────────────────────────────────────────────────────


def test_next_sort_order_empty_is_zero():
    assert next_sort_order([]) == 0


def test_next_sort_order_appends_after_max():
    assert next_sort_order([0, 1, 2]) == 3


def test_next_sort_order_uses_max_not_count():
    assert next_sort_order([0, 5, 2]) == 6
