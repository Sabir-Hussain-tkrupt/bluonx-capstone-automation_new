"""Pure-function tests for `check_start_date_feasibility` (Task 9.1).

  desired_start_date NULL                       → SKIPPED (no target)
  proposed NULL while desired present           → WARN (guard the gap)
  proposed > desired                            → WARN (with days_late)
  else                                          → PASS
"""

from __future__ import annotations

from datetime import date

from app.services.pre_award_validation_service import check_start_date_feasibility

DESIRED = date(2026, 7, 15)


def test_desired_null_skipped():
    r = check_start_date_feasibility(
        proposed_start_date=date(2026, 8, 1), desired_start_date=None
    )
    assert r["check"] == "start_date_feasibility"
    assert r["severity"] == "skipped"
    assert r["status"] == "skipped"


def test_proposed_null_with_desired_warns():
    r = check_start_date_feasibility(
        proposed_start_date=None, desired_start_date=DESIRED
    )
    assert r["severity"] == "warn"
    assert r["status"] == "fail"


def test_on_time_passes():
    r = check_start_date_feasibility(
        proposed_start_date=DESIRED, desired_start_date=DESIRED
    )
    assert r["severity"] == "pass"
    assert r["status"] == "pass"


def test_early_passes():
    r = check_start_date_feasibility(
        proposed_start_date=date(2026, 7, 10), desired_start_date=DESIRED
    )
    assert r["severity"] == "pass"


def test_late_warns_with_days_late():
    r = check_start_date_feasibility(
        proposed_start_date=date(2026, 7, 25), desired_start_date=DESIRED
    )
    assert r["severity"] == "warn"
    assert r["status"] == "fail"
    assert r["inputs"]["days_late"] == 10
