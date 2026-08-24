"""Unit tests for app/core/db_errors.

Deliberately narrow. The behavioural surface (409 vs 500, envelope, the
is_active branch, x-request-id) is verified against the live stack by curl.
What is covered here is the part that cannot be checked by eye and rots
silently: two regexes over strings that the postgrest driver supplies and could
reword in any release. If either parse breaks, the handler degrades to generic
copy instead of failing loudly, so a test is the only thing that would notice.
"""

from __future__ import annotations

import pytest
from postgrest.exceptions import APIError

from app.core import db_errors


# Verbatim shape of a real PostgREST 23505 on trades.name.
DUP_MESSAGE = 'duplicate key value violates unique constraint "trades_name_key"'
DUP_DETAILS = "Key (name)=(Geotechnical Engineering) already exists."


def make_error(**fields) -> APIError:
    """Build an APIError the way postgrest does, from the raw JSON body."""
    return APIError(fields)


# -- is_unique_violation -----------------------------------------------------


def test_23505_code_is_a_unique_violation():
    assert db_errors.is_unique_violation(
        make_error(code="23505", message=DUP_MESSAGE, details=DUP_DETAILS)
    )


def test_message_alone_is_enough_when_the_code_is_missing():
    """PostgREST does not always return a structured code; the nine existing
    per-service helpers fall back to the text for the same reason."""
    assert db_errors.is_unique_violation(make_error(message=DUP_MESSAGE))


@pytest.mark.parametrize(
    "code,message",
    [
        ("42501", "permission denied for table trades"),
        ("23503", 'insert violates foreign key constraint "tasks_trade_id_fkey"'),
        ("PGRST116", "JSON object requested, multiple (or no) rows returned"),
    ],
)
def test_other_sqlstates_are_not_unique_violations(code, message):
    assert not db_errors.is_unique_violation(make_error(code=code, message=message))


# -- constraint_name ---------------------------------------------------------


def test_constraint_name_is_parsed_from_the_message():
    exc = make_error(code="23505", message=DUP_MESSAGE, details=DUP_DETAILS)
    assert db_errors.constraint_name(exc) == "trades_name_key"


def test_partial_unique_index_name_is_parsed_too():
    """Partial indexes report under their index name, not a *_key name."""
    exc = make_error(
        code="23505",
        message='duplicate key value violates unique constraint "idx_awards_one_active_per_task"',
    )
    assert db_errors.constraint_name(exc) == "idx_awards_one_active_per_task"


def test_constraint_name_returns_none_when_unquoted():
    exc = make_error(code="23505", message="duplicate key value violates something")
    assert db_errors.constraint_name(exc) is None


def test_constraint_name_returns_none_on_an_empty_error():
    assert db_errors.constraint_name(make_error()) is None


# -- conflicting_value -------------------------------------------------------


def test_conflicting_value_is_parsed_from_details():
    exc = make_error(code="23505", message=DUP_MESSAGE, details=DUP_DETAILS)
    assert db_errors.conflicting_value(exc) == "Geotechnical Engineering"


def test_conflicting_value_keeps_a_closing_paren_inside_the_name():
    """The value pattern is greedy so a trade like "Paving (Phase 2)" survives."""
    exc = make_error(
        code="23505",
        message=DUP_MESSAGE,
        details="Key (name)=(Paving (Phase 2)) already exists.",
    )
    assert db_errors.conflicting_value(exc) == "Paving (Phase 2)"


def test_conflicting_value_handles_a_composite_key():
    exc = make_error(
        code="23505",
        details="Key (vendor_id, trade_id)=(abc, def) already exists.",
    )
    assert db_errors.conflicting_value(exc) == "abc, def"


@pytest.mark.parametrize(
    "details",
    [None, "", "some other wording entirely", "Key (name)=() already exists."],
)
def test_conflicting_value_returns_none_on_unexpected_details(details):
    assert db_errors.conflicting_value(make_error(details=details)) is None
