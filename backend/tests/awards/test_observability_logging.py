"""Structured observability logging in the pre-award validator (Task 9.1).

A non-clean validation outcome (block or warn) must leave an INFO audit trail
naming the failing checks; a clean pass must stay quiet at INFO (DEBUG only) so
the common preview path doesn't spam the logs.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from app.services.pre_award_validation_service import (
    PreAwardContext,
    validate_pre_award,
)

LOGGER = "app.services.pre_award_validation_service"


def _ctx(**overrides) -> PreAwardContext:
    base = dict(
        award_amount=Decimal("100000.00"),
        is_superseded=False,
        is_draft=False,
        submission_status="submitted",
        proposed_start_date=date(2026, 7, 10),
        insurance_expiration_date=date(2099, 1, 1),
        bonding_capacity=Decimal("200000.00"),
        max_active_jobs=5,
        current_active_jobs=2,
        budget_estimate=Decimal("100000.00"),
        estimated_end_date=date(2098, 12, 31),
        desired_start_date=date(2026, 7, 15),
        today=date(2026, 6, 18),
    )
    base.update(overrides)
    return PreAwardContext(**base)


def test_blocking_outcome_logs_info_with_check_name(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        validate_pre_award(_ctx(is_superseded=True))
    recs = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]
    assert recs, "expected an INFO log for a blocking validation"
    assert any("submission_eligibility" in r.getMessage() for r in recs)


def test_warning_outcome_logs_info(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        validate_pre_award(_ctx(bonding_capacity=None))  # bonding warn, no block
    recs = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]
    assert recs, "expected an INFO log for a warning validation"
    assert any("bonding_capacity" in r.getMessage() for r in recs)


def test_clean_outcome_stays_quiet_at_info(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        validate_pre_award(_ctx())
    recs = [r for r in caplog.records if r.name == LOGGER and r.levelno >= logging.INFO]
    assert not recs, "a clean validation should not log at INFO"
