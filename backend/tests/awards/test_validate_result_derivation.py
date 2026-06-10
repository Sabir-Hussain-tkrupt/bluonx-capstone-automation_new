"""Tests for `validate_pre_award` result-object derivation (Task 9.1).

Derivation rules:
  has_blocking      = any check.severity == "block"
  has_warnings      = any check.severity == "warn"
  can_award         = not has_blocking
  requires_override = has_warnings and not has_blocking
Result is byte-compatible with what awards.validation_results will store.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

from app.services.pre_award_validation_service import (
    RUBRIC_VERSION,
    PreAwardContext,
    validate_pre_award,
)

TODAY = date(2026, 6, 10)

# A context where every check passes (no warns, no blocks, no skips).
_CLEAN = PreAwardContext(
    award_amount=Decimal("100000.00"),
    is_superseded=False,
    is_draft=False,
    submission_status="submitted",
    proposed_start_date=date(2026, 7, 10),
    insurance_expiration_date=date(2027, 1, 1),
    bonding_capacity=Decimal("200000.00"),
    max_active_jobs=5,
    current_active_jobs=2,
    budget_estimate=Decimal("100000.00"),
    estimated_end_date=date(2026, 12, 31),
    desired_start_date=date(2026, 7, 15),
    today=TODAY,
)


def _ctx(**overrides) -> PreAwardContext:
    return dataclasses.replace(_CLEAN, **overrides)


def test_all_pass_clean_award():
    res = validate_pre_award(_CLEAN)
    assert res["rubric_version"] == RUBRIC_VERSION
    assert len(res["checks"]) == 6
    assert res["has_blocking"] is False
    assert res["has_warnings"] is False
    assert res["can_award"] is True
    assert res["requires_override"] is False
    assert res["validated_at"]  # ISO timestamp present
    assert res["award_amount"] == Decimal("100000.00")


def test_warns_only_requires_override():
    res = validate_pre_award(_ctx(bonding_capacity=None))
    assert res["has_blocking"] is False
    assert res["has_warnings"] is True
    assert res["can_award"] is True
    assert res["requires_override"] is True


def test_one_block_cannot_award():
    res = validate_pre_award(_ctx(insurance_expiration_date=date(2026, 6, 1)))
    assert res["has_blocking"] is True
    assert res["can_award"] is False
    assert res["requires_override"] is False


def test_block_plus_warn_override_not_offered():
    res = validate_pre_award(
        _ctx(insurance_expiration_date=date(2026, 6, 1), bonding_capacity=None)
    )
    assert res["has_blocking"] is True
    assert res["has_warnings"] is True
    assert res["can_award"] is False
    # override never offered while a block stands
    assert res["requires_override"] is False


def test_skipped_checks_do_not_block_or_warn():
    res = validate_pre_award(
        _ctx(budget_estimate=None, max_active_jobs=None, desired_start_date=None)
    )
    severities = {c["check"]: c["severity"] for c in res["checks"]}
    assert severities["budget_variance"] == "skipped"
    assert severities["vendor_capacity"] == "skipped"
    assert severities["start_date_feasibility"] == "skipped"
    assert res["can_award"] is True
    assert res["has_warnings"] is False
    assert res["requires_override"] is False
