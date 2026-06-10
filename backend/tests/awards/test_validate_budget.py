"""Pure-function tests for `check_budget_variance` (Task 9.1).

±5% band around tasks.budget_estimate.
  budget_estimate NULL                     → SKIPPED
  abs(award - estimate)/estimate > 0.05    → WARN (with direction + variance_pct)
  else                                     → PASS
"""

from __future__ import annotations

from decimal import Decimal

from app.services.pre_award_validation_service import check_budget_variance

ESTIMATE = Decimal("100000.00")


def test_null_estimate_skipped():
    r = check_budget_variance(award_amount=ESTIMATE, budget_estimate=None)
    assert r["check"] == "budget_variance"
    assert r["severity"] == "skipped"
    assert r["status"] == "skipped"


def test_over_band_warns_over():
    r = check_budget_variance(
        award_amount=Decimal("110000.00"), budget_estimate=ESTIMATE
    )
    assert r["severity"] == "warn"
    assert r["status"] == "fail"
    assert r["inputs"]["direction"] == "over"
    assert r["inputs"]["variance_pct"] == 10.0


def test_under_band_warns_under():
    r = check_budget_variance(
        award_amount=Decimal("90000.00"), budget_estimate=ESTIMATE
    )
    assert r["severity"] == "warn"
    assert r["inputs"]["direction"] == "under"
    assert r["inputs"]["variance_pct"] == 10.0


def test_at_5pct_boundary_passes():
    # exactly 5% over is NOT > 0.05 → PASS
    r = check_budget_variance(
        award_amount=Decimal("105000.00"), budget_estimate=ESTIMATE
    )
    assert r["severity"] == "pass"
    assert r["status"] == "pass"


def test_within_band_passes():
    r = check_budget_variance(
        award_amount=Decimal("102000.00"), budget_estimate=ESTIMATE
    )
    assert r["severity"] == "pass"
