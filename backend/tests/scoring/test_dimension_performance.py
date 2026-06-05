"""Pure-function tests for `score_performance` (Task 8.2).

Placeholder until Phase 10 (milestone data + flag history). See
/docs/DEFERRED.md > Past Performance Scoring.
"""

from __future__ import annotations

from uuid import uuid4

from app.services.bid_scoring_service import (
    NEUTRAL_PERFORMANCE_SCORE,
    score_performance,
)


def test_returns_neutral_performance_constant():
    assert score_performance(uuid4()) == NEUTRAL_PERFORMANCE_SCORE


def test_neutral_performance_constant_is_75():
    # Pin the constant value — changing it is a deliberate decision.
    assert NEUTRAL_PERFORMANCE_SCORE == 75.0


def test_returns_same_value_for_any_vendor_in_placeholder_state():
    a = score_performance(uuid4())
    b = score_performance(uuid4())
    assert a == b == NEUTRAL_PERFORMANCE_SCORE
