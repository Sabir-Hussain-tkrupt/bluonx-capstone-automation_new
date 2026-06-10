"""Pure-function tests for `check_submission_eligibility` (Task 9.1).

Live iff: not is_superseded AND not is_draft AND
          status IN ('submitted', 'under_review', 'accepted').
Anything else → BLOCK (status="fail"). This subsumes the awards.py:48-63
superseded guard into the validator.
"""

from __future__ import annotations

import pytest

from app.services.pre_award_validation_service import check_submission_eligibility


@pytest.mark.parametrize("status", ["submitted", "under_review", "accepted"])
def test_live_submission_passes(status):
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status=status
    )
    assert r["check"] == "submission_eligibility"
    assert r["severity"] == "pass"
    assert r["status"] == "pass"


def test_superseded_blocks():
    r = check_submission_eligibility(
        is_superseded=True, is_draft=False, status="submitted"
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"
    assert r["inputs"]["is_superseded"] is True


def test_draft_blocks():
    r = check_submission_eligibility(
        is_superseded=False, is_draft=True, status="draft"
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"
    assert r["inputs"]["is_draft"] is True


@pytest.mark.parametrize("status", ["draft", "rejected"])
def test_wrong_status_blocks(status):
    r = check_submission_eligibility(
        is_superseded=False, is_draft=False, status=status
    )
    assert r["severity"] == "block"
    assert r["status"] == "fail"
    assert r["inputs"]["status"] == status
