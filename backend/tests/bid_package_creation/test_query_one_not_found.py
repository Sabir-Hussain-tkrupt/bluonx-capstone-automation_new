"""Regression tests for `_query_one` not-found handling.

PostgREST's .single() raises an APIError (PGRST116) when zero rows match,
instead of returning an empty result. `_query_one` must translate that into
None so a missing task / template / vendor / contact / invitation surfaces as a
clean 4xx rather than crashing the request with a 500. Any other APIError must
still propagate.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.services.bid_package_service import _query_one


def _db_whose_single_raises(err: APIError) -> MagicMock:
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.side_effect = err
    db.table.return_value = chain
    return db


def test_query_one_returns_none_on_pgrst116():
    db = _db_whose_single_raises(
        APIError({"code": "PGRST116", "message": "JSON object requested, 0 rows returned"})
    )
    assert _query_one(db, "tasks", uuid4()) is None


def test_query_one_reraises_other_api_errors():
    db = _db_whose_single_raises(
        APIError({"code": "42501", "message": "permission denied for table tasks"})
    )
    with pytest.raises(APIError):
        _query_one(db, "tasks", uuid4())


def test_query_one_returns_row_when_present():
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    row = {"id": str(uuid4()), "name": "Rough Grading"}
    chain.execute.return_value = MagicMock(data=row)
    db.table.return_value = chain
    assert _query_one(db, "tasks", uuid4()) == row
