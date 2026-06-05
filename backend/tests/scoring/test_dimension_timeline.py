"""Pure-function tests for `score_timeline` (Task 8.2).

Days-late buckets:
  ≤0 → 100 · 1-7 → 75 · 8-14 → 50 · 15-30 → 25 · >30 → 0
Special:
  desired_start_date is None → 100 (cohort-constant; cancels out of ranking)
  desired present but proposed None → 0 (shouldn't happen — required on submit)
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.bid_scoring_service import score_timeline

DESIRED = date(2026, 7, 15)


def _proposed_with_lateness(days_late: int) -> date:
    return DESIRED + timedelta(days=days_late)


def test_desired_null_returns_100_regardless_of_proposed():
    assert score_timeline(date(2026, 7, 30), None) == 100.0


def test_desired_null_and_proposed_null_returns_100():
    assert score_timeline(None, None) == 100.0


def test_desired_present_proposed_null_returns_0():
    assert score_timeline(None, DESIRED) == 0.0


def test_on_time_returns_100():
    assert score_timeline(_proposed_with_lateness(0), DESIRED) == 100.0


def test_early_returns_100():
    assert score_timeline(_proposed_with_lateness(-5), DESIRED) == 100.0


def test_one_day_late_in_first_bucket_returns_75():
    assert score_timeline(_proposed_with_lateness(1), DESIRED) == 75.0


def test_seven_days_late_top_of_first_bucket_returns_75():
    assert score_timeline(_proposed_with_lateness(7), DESIRED) == 75.0


def test_eight_days_late_jumps_to_50():
    assert score_timeline(_proposed_with_lateness(8), DESIRED) == 50.0


def test_fourteen_days_late_top_of_second_bucket_returns_50():
    assert score_timeline(_proposed_with_lateness(14), DESIRED) == 50.0


def test_fifteen_days_late_jumps_to_25():
    assert score_timeline(_proposed_with_lateness(15), DESIRED) == 25.0


def test_thirty_days_late_top_of_third_bucket_returns_25():
    assert score_timeline(_proposed_with_lateness(30), DESIRED) == 25.0


def test_thirty_one_days_late_returns_0():
    assert score_timeline(_proposed_with_lateness(31), DESIRED) == 0.0


def test_very_late_returns_0():
    assert score_timeline(_proposed_with_lateness(365), DESIRED) == 0.0
