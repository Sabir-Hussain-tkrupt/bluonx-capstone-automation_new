"""Pure-function tests for `score_price` (Task 8.2)."""

from __future__ import annotations

from decimal import Decimal

from app.services.bid_scoring_service import score_price


def test_lone_bidder_gets_100():
    # Orchestrator passes lowest == this for a cohort of one.
    assert score_price(Decimal("50000"), Decimal("50000")) == 100.0


def test_lowest_bidder_gets_100():
    assert score_price(Decimal("80000"), Decimal("80000")) == 100.0


def test_ratio_math_higher_bid_lower_score():
    # 80000 / 100000 = 0.8 → 80.0
    assert score_price(Decimal("100000"), Decimal("80000")) == 80.0


def test_double_the_lowest_is_50():
    assert score_price(Decimal("100000"), Decimal("50000")) == 50.0


def test_clamped_to_100_when_inputs_equal():
    # Defensive: if upstream ever passed lowest > this (shouldn't happen),
    # we still cap at 100.
    assert score_price(Decimal("90000"), Decimal("100000")) == 100.0


def test_equal_totals_all_100():
    assert score_price(Decimal("75000.00"), Decimal("75000.00")) == 100.0
