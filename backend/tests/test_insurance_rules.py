"""
Unit tests for classify_insurance — the shared insurance classifier used by
both vendor filtering and pre-award validation.
"""

from datetime import date, timedelta

import pytest

from app.services.insurance_rules import classify_insurance


TODAY = date(2026, 6, 1)
YESTERDAY = TODAY - timedelta(days=1)
NEXT_WEEK = TODAY + timedelta(days=7)
NEXT_YEAR = TODAY + timedelta(days=365)
LAST_MONTH = TODAY - timedelta(days=30)


def test_missing_certificate():
    assert classify_insurance(None, NEXT_YEAR, TODAY) == "missing"


def test_expired_before_today():
    assert classify_insurance(YESTERDAY, NEXT_YEAR, TODAY) == "expired"


def test_expiring_exactly_today_is_not_expired():
    # strict `<` — a cert dated today is valid through today. With no horizon
    # to under-cover, that's "ok" (isolates the today boundary of the expired
    # check; a future project_end would legitimately make it lapses_before_end).
    assert classify_insurance(TODAY, None, TODAY) == "ok"
    assert classify_insurance(TODAY, TODAY, TODAY) == "ok"


def test_lapses_between_today_and_project_end():
    assert classify_insurance(NEXT_WEEK, NEXT_YEAR, TODAY) == "lapses_before_end"


def test_expiring_exactly_on_project_end_covers_the_project():
    # strict `<` — a cert ending on the end date covers the whole project.
    assert classify_insurance(NEXT_YEAR, NEXT_YEAR, TODAY) == "ok"


def test_valid_past_project_end():
    assert classify_insurance(NEXT_YEAR, NEXT_WEEK, TODAY) == "ok"


def test_no_project_end_collapses_to_today_only():
    # A vendor valid today with no known horizon is ok, never "lapses".
    assert classify_insurance(NEXT_WEEK, None, TODAY) == "ok"
    assert classify_insurance(YESTERDAY, None, TODAY) == "expired"


def test_overdue_project_does_not_mask_a_valid_certificate():
    # project_end in the past + a currently-valid cert → ok, no false lapse.
    assert classify_insurance(NEXT_WEEK, LAST_MONTH, TODAY) == "ok"


def test_overdue_project_still_catches_a_truly_expired_certificate():
    # The reported bug: with the old single past-cutoff, a cert that expired
    # yesterday slipped through. The hard "expired" check is against today, so
    # it is caught regardless of how stale the project end date is.
    assert classify_insurance(YESTERDAY, LAST_MONTH, TODAY) == "expired"
