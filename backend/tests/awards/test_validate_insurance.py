"""Pure-function tests for `check_insurance_validity` (Task 9.1).

  expiration < today                          → BLOCK (uninsurable; not overridable)
  valid today but expiration < est_end_date   → WARN  (lapses mid-work; overridable)
  est_end_date NULL → compare to today only   → PASS
  insurance_expiration_date NULL              → WARN  (data gap)
"""

from __future__ import annotations

from datetime import date

from app.services.pre_award_validation_service import check_insurance_validity

TODAY = date(2026, 6, 10)
EST_END = date(2026, 12, 31)


def test_expired_blocks():
    r = check_insurance_validity(
        insurance_expiration_date=date(2026, 6, 9),
        estimated_end_date=EST_END,
        today=TODAY,
    )
    assert r["check"] == "insurance_validity"
    assert r["severity"] == "block"
    assert r["status"] == "fail"


def test_lapses_before_project_end_warns():
    # valid today (>= today) but expires before estimated_end_date
    r = check_insurance_validity(
        insurance_expiration_date=date(2026, 9, 1),
        estimated_end_date=EST_END,
        today=TODAY,
    )
    assert r["severity"] == "warn"
    assert r["status"] == "fail"


def test_valid_through_project_end_passes():
    r = check_insurance_validity(
        insurance_expiration_date=date(2027, 1, 1),
        estimated_end_date=EST_END,
        today=TODAY,
    )
    assert r["severity"] == "pass"
    assert r["status"] == "pass"


def test_valid_today_at_boundary_passes():
    # expiration == today is not "< today", so not expired.
    r = check_insurance_validity(
        insurance_expiration_date=TODAY,
        estimated_end_date=None,
        today=TODAY,
    )
    assert r["severity"] == "pass"


def test_est_end_null_valid_today_passes():
    r = check_insurance_validity(
        insurance_expiration_date=date(2026, 6, 15),
        estimated_end_date=None,
        today=TODAY,
    )
    assert r["severity"] == "pass"
    assert r["status"] == "pass"


def test_expiration_null_warns():
    r = check_insurance_validity(
        insurance_expiration_date=None,
        estimated_end_date=EST_END,
        today=TODAY,
    )
    assert r["severity"] == "warn"
    assert r["status"] == "fail"
