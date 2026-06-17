"""Pure-function tests for `check_submission_eligibility` (Task 9.1).

Live iff: not is_superseded AND not is_draft AND
          status IN ('submitted', 'under_review', 'accepted')
          AND award_amount is a positive number.
Anything else → BLOCK (status="fail"). This subsumes the awards.py:48-63
superseded guard into the validator, and gates a missing/zero bid amount so a
NULL total_amount can never reach the NOT NULL awards.award_amount column.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.pre_award_validation_service import check_submission_eligibility

VALID_AMOUNT = Decimal("100000.00")


@pytest.mark.parametrize("status", ["submitted", "under_review", "accepted"])
def test_live_submission_passes(status):
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status=status, award_amount=VALID_AMOUNT
    )
    assert r["check"] == "submission_eligibility"
    assert r["severity"] == "pass"
    assert r["status"] == "pass"


def test_superseded_blocks():
    r = check_submission_eligibility(
        is_superseded=True, is_draft=False, status="submitted", award_amount=VALID_AMOUNT
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"
    assert r["inputs"]["is_superseded"] is True


def test_draft_blocks():
    r = check_submission_eligibility(
        is_superseded=False, is_draft=True, status="draft", award_amount=VALID_AMOUNT
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"
    assert r["inputs"]["is_draft"] is True


@pytest.mark.parametrize("status", ["draft", "rejected"])
def test_wrong_status_blocks(status):
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status=status, award_amount=VALID_AMOUNT
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"
    assert r["inputs"]["status"] == status


# ── award_amount gate (the NULL/zero total_amount → 500 fix) ──────────────


def test_null_amount_blocks():
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status="submitted", award_amount=None
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"
    assert r["inputs"]["award_amount"] is None


def test_zero_amount_blocks():
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status="submitted",
        award_amount=Decimal("0"),
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"


def test_negative_amount_blocks():
    # Schema CHECK(total_amount >= 0) should prevent this, but the gate is
    # defensive against dirty imports / synthetic rows.
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status="submitted",
        award_amount=Decimal("-1"),
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"


def test_eligibility_inputs_carry_amount():
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status="submitted", award_amount=VALID_AMOUNT
    )
    assert r["inputs"]["award_amount"] == str(VALID_AMOUNT)
