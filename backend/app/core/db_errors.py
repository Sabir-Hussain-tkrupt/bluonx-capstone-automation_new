"""Central translation of Supabase/PostgREST errors into HTTP responses.

Why this exists
---------------
Postgres raises SQLSTATE 23505 on a unique violation. supabase-py wraps it in
`postgrest.exceptions.APIError`. A router that does not catch that lets it
escape as a bare 500 with a `text/plain` body, which is neither actionable for
the caller nor greppable in the logs.

Most write paths already catch `APIError` locally and raise a specific
`HTTPException` (see `_is_unique_violation` in award_service, contract_service,
holiday_service, review_service, and five others). Those keep working exactly as
before: a local `except` consumes the exception, so the handler registered here
never sees it. Local handling wins, by construction. This module is the net
underneath the paths that have no local catch.

Scope of the net
----------------
`APIError` is raised by PostgREST table calls and by `db.rpc(...)`, which share
the same transport. Storage raises `storage3.exceptions.StorageApiError` and
auth raises `supabase_auth.errors.AuthApiError`; neither subclasses `APIError`
and neither carries a SQLSTATE, so neither is affected.

Reading the exception
---------------------
`APIError` exposes `code`, `message`, `details`, and `hint`. There is NO
attribute holding the constraint name: it is embedded in `message`, so it has to
be parsed out. A representative 23505 looks like::

    code    = "23505"
    message = 'duplicate key value violates unique constraint "trades_name_key"'
    details = "Key (name)=(Geotechnical Engineering) already exists."

Both parses are best-effort and return None rather than raising, because the
wording is driver-supplied and can change under us. A None result degrades to
generic copy; it never crashes the handler.

Correlation ids
---------------
Responses produced here pass back through `RequestLoggingMiddleware.send_wrapper`
and therefore carry `x-request-id`. An uncaught exception does not: Starlette's
`ServerErrorMiddleware` sits above all user middleware and writes its plain-text
500 using the raw ASGI send, bypassing the wrapper that stamps the header. That
is the other half of the bug this module fixes.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

# Postgres unique-violation SQLSTATE.
_UNIQUE_VIOLATION = "23505"

_GENERIC_CONFLICT = "A record with these values already exists."
_GENERIC_SERVER_ERROR = "An unexpected database error occurred."

# 'duplicate key value violates unique constraint "trades_name_key"'
_CONSTRAINT_RE = re.compile(r'constraint "([^"]+)"')

# 'Key (name)=(Geotechnical Engineering) already exists.'
# Greedy on the value so a name containing ")" survives the parse.
_DETAIL_VALUE_RE = re.compile(r"^Key \([^)]*\)=\((.*)\) already exists\.?$")


def is_unique_violation(exc: APIError) -> bool:
    """True when `exc` is a Postgres unique violation.

    Same heuristic the nine existing per-service helpers use: trust `.code`
    first, fall back to the message text for the paths where PostgREST returns
    the error without a structured code.
    """
    if getattr(exc, "code", None) == _UNIQUE_VIOLATION:
        return True
    text = str(exc).lower()
    return "duplicate key" in text or "unique constraint" in text


def constraint_name(exc: APIError) -> str | None:
    """The violated constraint's name, parsed out of the driver message.

    None when the message does not name one, which is the signal to fall back to
    generic copy.
    """
    message = getattr(exc, "message", None) or str(exc)
    match = _CONSTRAINT_RE.search(str(message))
    return match.group(1) if match else None


def conflicting_value(exc: APIError) -> str | None:
    """The offending value, parsed out of `.details`.

    None when `.details` is absent or does not match the expected wording.
    """
    details = getattr(exc, "details", None)
    if not details:
        return None
    match = _DETAIL_VALUE_RE.match(str(details).strip())
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


# -- Per-constraint messages -------------------------------------------------
#
# Keys are constraint names as Postgres reports them. Values are either a plain
# string or a resolver that may consult the request (and therefore the database)
# to say something more specific. Adding a constraint is a one-line change.
#
# A resolver runs inside the exception handler, so it must never raise. The
# handler wraps every call in a try/except as a backstop, but resolvers should
# still degrade on their own where they can.


def _trades_name_conflict(request: Request, exc: APIError) -> str:
    """Message for a duplicate `trades.name`.

    `trades` has no soft delete: retirement flips `is_active` to false and the
    row keeps its name (rls_policies.sql, "No DELETE policy. Trades use
    is_active flag"). So an inactive trade still reserves the name while being
    invisible in the UI, and a flat "already exists" would send the admin
    looking for a row they cannot see. Hence the lookup and the two messages.

    The SELECT runs AFTER the conflict, so it is not a pre-check and cannot
    race the insert: the database has already ruled. It only decides wording.
    """
    name = conflicting_value(exc)
    if not name:
        return "A trade with that name already exists."

    active_message = f'A trade named "{name}" already exists.'
    inactive_message = (
        f'A trade named "{name}" already exists but is inactive. '
        "Reactivate it instead of creating a new one."
    )

    try:
        db = request.app.state.supabase
        response = (
            db.table("trades")
            .select("is_active")
            .eq("name", name)
            .maybe_single()
            .execute()
        )
        # maybe_single() returns None (not a response with data=None) on zero
        # rows, so guard the response itself before touching .data.
        if not response or not response.data:
            return active_message
        return active_message if response.data.get("is_active") else inactive_message
    except Exception:  # noqa: BLE001 - wording must never take the request down
        logger.warning(
            "Could not read trade is_active for conflict message", exc_info=True
        )
        return active_message


_CONSTRAINT_MESSAGES: dict[str, str | Callable[[Request, APIError], str]] = {
    "trades_name_key": _trades_name_conflict,
}


def _conflict_detail(request: Request, exc: APIError) -> str:
    """Resolve the 409 body, degrading to generic copy at every failure point."""
    name = constraint_name(exc)
    if not name:
        return _GENERIC_CONFLICT

    entry = _CONSTRAINT_MESSAGES.get(name)
    if entry is None:
        # Known-shape conflict on a constraint nobody has written copy for yet.
        # Still a 409, never a crash and never a 500.
        logger.info("Unique violation on unmapped constraint %s", name)
        return _GENERIC_CONFLICT

    if isinstance(entry, str):
        return entry

    try:
        return entry(request, exc)
    except Exception:  # noqa: BLE001 - a broken resolver must not become a 500
        logger.exception("Conflict message resolver failed for constraint %s", name)
        return _GENERIC_CONFLICT


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Global handler for PostgREST errors that no router caught.

    23505 becomes a 409 with a human-readable body. Everything else keeps its
    current behaviour of a 500, logged in full with the original error, and with
    nothing from the driver leaked into the response body.
    """
    if is_unique_violation(exc):
        return JSONResponse(
            status_code=409,
            content={"detail": _conflict_detail(request, exc)},
        )

    logger.error(
        "Unhandled Supabase APIError on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": _GENERIC_SERVER_ERROR})
