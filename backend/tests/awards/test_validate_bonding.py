"""Pure-function tests for `check_bonding_capacity` (Task 9.1).

  bonding_capacity < award_amount → WARN (insufficient bonding)
  bonding_capacity NULL           → WARN (data gap)
  else                            → PASS
"""

from __future__ import annotations

from decimal import Decimal

from app.services.pre_award_validation_service import check_bonding_capacity

AWARD = Decimal("100000.00")


def test_below_award_warns():
    r = check_bonding_capacity(bonding_capacity=Decimal("50000.00"), award_amount=AWARD)
    assert r["check"] == "bonding_capacity"
    assert r["severity"] == "warn"
    assert r["status"] == "fail"


def test_equal_passes():
    r = check_bonding_capacity(bonding_capacity=AWARD, award_amount=AWARD)
    assert r["severity"] == "pass"
    assert r["status"] == "pass"


def test_above_award_passes():
    r = check_bonding_capacity(
        bonding_capacity=Decimal("250000.00"), award_amount=AWARD
    )
    assert r["severity"] == "pass"


def test_null_bonding_warns():
    r = check_bonding_capacity(bonding_capacity=None, award_amount=AWARD)
    assert r["severity"] == "warn"
    assert r["status"] == "fail"
