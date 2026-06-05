"""Warning-flag boundary tests for Task 8.4 recommendation builder.

One boundary case per flag transition; each test builds a single-row cohort
with the exact `scoring_metadata.inputs` shape needed.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.bid_recommendation_service import build_recommendation

from .conftest import make_row


DEADLINE = date(2026, 7, 1)
HORIZON = DEADLINE + timedelta(days=30)


def _flags(row, budget):
    return build_recommendation([row], budget)["ranking"][0]["warning_flags"]


# ── over_budget ─────────────────────────────────────────────────────────


def test_over_budget_strict_greater_than_flags():
    row = make_row(this_total="600000.00")
    assert "over_budget" in _flags(row, Decimal("500000"))


def test_over_budget_equal_to_budget_does_not_flag():
    row = make_row(this_total="500000.00")
    assert "over_budget" not in _flags(row, Decimal("500000"))


def test_over_budget_under_budget_does_not_flag():
    row = make_row(this_total="400000.00")
    assert "over_budget" not in _flags(row, Decimal("500000"))


def test_over_budget_suppressed_when_budget_is_none():
    """NULL budget → no over_budget flag, regardless of this_total."""
    row = make_row(this_total="9999999.00")
    assert "over_budget" not in _flags(row, None)


# ── late_start ──────────────────────────────────────────────────────────


def test_late_start_proposed_after_desired_flags():
    row = make_row(
        proposed_start_date=date(2026, 7, 20),
        desired_start_date=date(2026, 7, 15),
    )
    assert "late_start" in _flags(row, Decimal("500000"))


def test_late_start_proposed_equals_desired_does_not_flag():
    """Vendor saying 'yes I can hit your date' (Task 8.1.5 calendar-invite model)."""
    row = make_row(
        proposed_start_date=date(2026, 7, 15),
        desired_start_date=date(2026, 7, 15),
    )
    assert "late_start" not in _flags(row, Decimal("500000"))


def test_late_start_proposed_before_desired_does_not_flag():
    row = make_row(
        proposed_start_date=date(2026, 7, 10),
        desired_start_date=date(2026, 7, 15),
    )
    assert "late_start" not in _flags(row, Decimal("500000"))


def test_late_start_suppressed_when_basis_is_no_desired_date():
    """basis suppression takes precedence even if dates somehow exist on the row."""
    row = make_row(
        proposed_start_date=date(2026, 8, 1),
        desired_start_date=date(2026, 7, 15),
        basis="no_desired_date",
    )
    assert "late_start" not in _flags(row, Decimal("500000"))


def test_late_start_skipped_when_desired_null():
    row = make_row(
        proposed_start_date=date(2026, 8, 1),
        desired_start_date=None,
    )
    assert "late_start" not in _flags(row, Decimal("500000"))


def test_late_start_skipped_when_proposed_null():
    row = make_row(
        proposed_start_date=None,
        desired_start_date=date(2026, 7, 15),
    )
    assert "late_start" not in _flags(row, Decimal("500000"))


# ── insurance_window ────────────────────────────────────────────────────


def test_insurance_window_null_expiration_flags():
    row = make_row(insurance_expiration=None, deadline=DEADLINE)
    assert "insurance_window" in _flags(row, Decimal("500000"))


def test_insurance_window_expiration_before_deadline_flags():
    row = make_row(insurance_expiration=DEADLINE - timedelta(days=1),
                   deadline=DEADLINE)
    assert "insurance_window" in _flags(row, Decimal("500000"))


def test_insurance_window_expiration_equal_deadline_flags():
    """At exactly the deadline → still within deadline+30d, so flagged."""
    row = make_row(insurance_expiration=DEADLINE, deadline=DEADLINE)
    assert "insurance_window" in _flags(row, Decimal("500000"))


def test_insurance_window_expiration_one_day_before_horizon_flags():
    row = make_row(insurance_expiration=HORIZON - timedelta(days=1),
                   deadline=DEADLINE)
    assert "insurance_window" in _flags(row, Decimal("500000"))


def test_insurance_window_expiration_exactly_at_horizon_does_not_flag():
    """deadline + 30d is the safe boundary; matches the 8.2 rubric (score=100)."""
    row = make_row(insurance_expiration=HORIZON, deadline=DEADLINE)
    assert "insurance_window" not in _flags(row, Decimal("500000"))


def test_insurance_window_expiration_after_horizon_does_not_flag():
    row = make_row(insurance_expiration=HORIZON + timedelta(days=1),
                   deadline=DEADLINE)
    assert "insurance_window" not in _flags(row, Decimal("500000"))


# ── onboarding_incomplete ───────────────────────────────────────────────


def test_onboarding_complete_does_not_flag():
    row = make_row(onboarding_status="complete")
    assert "onboarding_incomplete" not in _flags(row, Decimal("500000"))


def test_onboarding_partial_flags():
    row = make_row(onboarding_status="partial")
    assert "onboarding_incomplete" in _flags(row, Decimal("500000"))


def test_onboarding_pending_flags():
    row = make_row(onboarding_status="pending")
    assert "onboarding_incomplete" in _flags(row, Decimal("500000"))


def test_onboarding_none_flags():
    row = make_row(onboarding_status=None)
    assert "onboarding_incomplete" in _flags(row, Decimal("500000"))


# ── Combinations ────────────────────────────────────────────────────────


def test_all_four_flags_present_in_documented_order():
    """A vendor that triggers every flag → all four codes appear in a stable
    documented order (over_budget, late_start, insurance_window,
    onboarding_incomplete)."""
    row = make_row(
        this_total="600000.00",
        proposed_start_date=date(2026, 8, 1),
        desired_start_date=date(2026, 7, 15),
        insurance_expiration=None,
        onboarding_status="pending",
        deadline=DEADLINE,
    )
    flags = _flags(row, Decimal("500000"))
    assert flags == [
        "over_budget",
        "late_start",
        "insurance_window",
        "onboarding_incomplete",
    ]


def test_clean_vendor_has_no_flags():
    row = make_row(
        this_total="400000.00",
        proposed_start_date=date(2026, 7, 15),
        desired_start_date=date(2026, 7, 15),
        insurance_expiration=HORIZON,
        onboarding_status="complete",
        deadline=DEADLINE,
    )
    assert _flags(row, Decimal("500000")) == []
