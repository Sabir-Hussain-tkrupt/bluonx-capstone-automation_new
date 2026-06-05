"""Pure-function tests for `score_capacity` (Task 8.2).

available = max(max_active_jobs - current_active_jobs, 0)
capacity_score = available / max_active_jobs * 100
  - max_active_jobs is None → NEUTRAL_CAPACITY_SCORE (75.0)
  - max_active_jobs == 0    → 0.0
"""

from __future__ import annotations

from app.services.bid_scoring_service import (
    NEUTRAL_CAPACITY_SCORE,
    score_capacity,
)


def test_max_null_returns_neutral_75():
    assert score_capacity(None, 3) == NEUTRAL_CAPACITY_SCORE == 75.0


def test_max_zero_returns_0():
    assert score_capacity(0, 0) == 0.0


def test_full_availability_returns_100():
    assert score_capacity(5, 0) == 100.0


def test_half_used_returns_60_when_2_of_5():
    # max=5, current=2 → available=3 → 60.0
    assert score_capacity(5, 2) == 60.0


def test_at_capacity_returns_0():
    assert score_capacity(5, 5) == 0.0


def test_current_exceeds_max_is_clamped_to_0():
    # Should never happen (DB trigger maintains current_active_jobs), but
    # guard against negative score.
    assert score_capacity(5, 7) == 0.0


def test_current_active_default_zero_is_full_capacity():
    assert score_capacity(10, 0) == 100.0
