"""Task 8.1.5 — pure unit tests on validate_for_submit's new
required-when-desired-present rule for proposed_start_date.
"""

from __future__ import annotations

import pytest

from app.services.vendor_portal_submit_validator import validate_for_submit


def _base_submission(**overrides) -> dict:
    """A submission dict that would otherwise PASS validation —
    isolates the proposed_start_date rule."""
    row = {
        "vendor_notes": "ok",
        "total_amount": "1000.00",
        "proposed_start_date": None,
    }
    row.update(overrides)
    return row


def _no_errors_except_proposed(errors):
    return [e for e in errors if e.field == "proposed_start_date"]


def test_null_proposed_with_desired_present_rejects():
    errs = validate_for_submit(
        submission=_base_submission(proposed_start_date=None),
        line_items=[],
        template_items=[],
        is_lump_sum_template=True,
        package_has_desired_date=True,
    )
    matches = _no_errors_except_proposed(errs)
    assert len(matches) == 1
    assert "required" in matches[0].message.lower()


def test_null_proposed_without_desired_passes():
    errs = validate_for_submit(
        submission=_base_submission(proposed_start_date=None),
        line_items=[],
        template_items=[],
        is_lump_sum_template=True,
        package_has_desired_date=False,
    )
    assert _no_errors_except_proposed(errs) == []


def test_proposed_present_with_desired_present_passes():
    errs = validate_for_submit(
        submission=_base_submission(proposed_start_date="2026-09-15"),
        line_items=[],
        template_items=[],
        is_lump_sum_template=True,
        package_has_desired_date=True,
    )
    assert _no_errors_except_proposed(errs) == []


def test_proposed_present_without_desired_passes():
    errs = validate_for_submit(
        submission=_base_submission(proposed_start_date="2026-09-15"),
        line_items=[],
        template_items=[],
        is_lump_sum_template=True,
        package_has_desired_date=False,
    )
    assert _no_errors_except_proposed(errs) == []


def test_empty_string_treated_as_null():
    errs = validate_for_submit(
        submission=_base_submission(proposed_start_date=""),
        line_items=[],
        template_items=[],
        is_lump_sum_template=True,
        package_has_desired_date=True,
    )
    matches = _no_errors_except_proposed(errs)
    assert len(matches) == 1
