"""Pure-function tests for `score_performance` (Phase 10).

The dimension is now backed by real per-vendor review data: the orchestrator reads
v_vendor_performance and passes a `perf_map`; the function stays pure and only looks
up its value, falling back to the neutral 75 when a vendor has no reviews.
"""

from __future__ import annotations

from uuid import uuid4

from app.services.bid_scoring_service import (
    NEUTRAL_PERFORMANCE_SCORE,
    score_performance,
)


def test_vendor_with_reviews_returns_mapped_score():
    vendor_id = uuid4()
    # performance_score is the view's avg/5*100 (rating 4 → 80.00).
    perf_map = {str(vendor_id): {"performance_score": "80.00", "review_count": 1}}
    assert score_performance(vendor_id, perf_map) == 80.0


def test_vendor_without_reviews_falls_back_to_neutral():
    assert score_performance(uuid4(), {}) == NEUTRAL_PERFORMANCE_SCORE


def test_absent_performance_score_falls_back_to_neutral():
    vendor_id = uuid4()
    perf_map = {str(vendor_id): {"performance_score": None, "review_count": 0}}
    assert score_performance(vendor_id, perf_map) == NEUTRAL_PERFORMANCE_SCORE


def test_neutral_performance_constant_is_75():
    # Pin the constant value — changing it is a deliberate decision.
    assert NEUTRAL_PERFORMANCE_SCORE == 75.0


def test_stays_pure_no_db_argument():
    # Signature is (vendor_id, perf_map) — no DB client is threaded in.
    import inspect

    params = list(inspect.signature(score_performance).parameters)
    assert params == ["vendor_id", "perf_map"]
