"""Pure-function tests for `score_compliance` (Task 8.2).

Mean of two components:
  - onboarding: complete=100, partial=50, pending=0
  - insurance vs deadline + 30d horizon: >=horizon=100, >=deadline=50, else=0
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.bid_scoring_service import score_compliance

DEADLINE = date(2026, 7, 1)
HORIZON = DEADLINE + timedelta(days=30)  # 2026-07-31


def test_complete_and_well_beyond_horizon_is_100():
    assert score_compliance("complete", date(2027, 1, 1), DEADLINE) == 100.0


def test_partial_and_in_window_is_50():
    # onboarding 50 + insurance 50 → mean 50
    assert score_compliance("partial", date(2026, 7, 10), DEADLINE) == 50.0


def test_pending_and_expired_is_0():
    assert score_compliance("pending", date(2026, 6, 1), DEADLINE) == 0.0


def test_insurance_null_zeros_insurance_component():
    # onboarding 100 + insurance 0 → mean 50
    assert score_compliance("complete", None, DEADLINE) == 50.0


def test_insurance_exactly_at_deadline_is_50_component():
    # onboarding 100 + insurance 50 → mean 75
    assert score_compliance("complete", DEADLINE, DEADLINE) == 75.0


def test_insurance_exactly_at_horizon_is_100_component():
    # onboarding 100 + insurance 100 → mean 100
    assert score_compliance("complete", HORIZON, DEADLINE) == 100.0


def test_insurance_one_day_before_horizon_is_50_component():
    # onboarding 100 + insurance 50 → mean 75
    assert score_compliance(
        "complete", HORIZON - timedelta(days=1), DEADLINE
    ) == 75.0


def test_insurance_one_day_before_deadline_is_0_component():
    # onboarding 100 + insurance 0 → mean 50
    assert score_compliance(
        "complete", DEADLINE - timedelta(days=1), DEADLINE
    ) == 50.0


def test_unknown_onboarding_status_is_0_component():
    # onboarding 0 + insurance 100 → mean 50
    assert score_compliance("weird", date(2027, 1, 1), DEADLINE) == 50.0


def test_onboarding_none_treated_as_0():
    assert score_compliance(None, date(2027, 1, 1), DEADLINE) == 50.0
