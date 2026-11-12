"""Shared error handling for the financial module.

The financial stored procedures and guard triggers raise SQLSTATE PT403 / PT404 /
PT409 / PT422 with messages written for a person ("Budget line … is locked
(contract executed)…"). Services pass those through verbatim, exactly like
holiday_service does with its guardrail messages: no other layer can say it
better. Anything else is logged and becomes a generic message.
"""

from __future__ import annotations

import logging
from typing import Any

from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

_PT_STATUS = {"PT403": 403, "PT404": 404, "PT409": 409, "PT422": 422}


class FinancialError(Exception):
    """Raised by financial services; routers map it to an HTTPException.
    Mirrors HolidayError / MilestoneError / AwardError."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def _code(err: APIError) -> str:
    return str(getattr(err, "code", "") or "")


def _message(err: APIError) -> str:
    msg = getattr(err, "message", None)
    return str(msg) if msg else str(err)


def is_unique_violation(err: APIError) -> bool:
    text = str(err).lower()
    return _code(err) == "23505" or "duplicate key" in text


def to_financial_error(err: APIError, generic: str) -> FinancialError:
    """Translate a PostgREST error into a FinancialError with a useful message."""
    code = _code(err)
    if code in _PT_STATUS:
        return FinancialError(_PT_STATUS[code], _message(err))
    for pt, status in _PT_STATUS.items():  # some paths surface the code only in text
        if pt in str(err):
            return FinancialError(status, _message(err))
    if is_unique_violation(err):
        return FinancialError(409, "A record with these values already exists.")
    if code == "23514":  # check_violation
        return FinancialError(422, "The values break a validation rule. Please review and try again.")
    logger.error("Unexpected database error: %s", err)
    return FinancialError(500, generic)


def call_rpc(db, name: str, params: dict, generic: str) -> Any:
    """Run an RPC and map its errors. Returns `.data` (list / dict / scalar)."""
    try:
        resp = db.rpc(name, params).execute()
    except APIError as exc:
        raise to_financial_error(exc, generic) from exc
    return resp.data if resp is not None else None


def first(data: Any) -> dict | None:
    """RETURNS SETOF → list; tolerate a bare dict too."""
    if isinstance(data, list):
        return data[0] if data else None
    return data or None


def money(value: Any) -> str | None:
    """Decimals go to PostgREST as strings so json never sees a float."""
    return None if value is None else str(value)
