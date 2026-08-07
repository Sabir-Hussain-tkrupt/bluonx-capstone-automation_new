"""
Milestone check-in response recorder (Phase 10.2).

The authenticated write half of the vendor check-in flow. Delegates the actual
state change to the `fn_record_milestone_response` RPC, which records the
response, runs `transition_milestone`, and spends the token in ONE transaction
(supabase-py has no client transactions). This layer only shapes params,
supplies business-timezone "today", and maps the RPC's SQLSTATEs to HTTP.

Concurrency / first-response-wins lives entirely in the RPC:
  - UNIQUE(milestone_alert_id) on milestone_responses ⇒ a concurrent second
    click loses and comes back as outcome='already_answered' (never a 500).
  - a transition PT409 (milestone moved terminal) rolls the response insert
    back ⇒ surfaced as 410 (no longer current), never an orphan row.

This layer also owns the PM fan-out, because the RPC cannot: a stored procedure
can neither send email nor write an in-app notification. See
`_notify_pm_of_outcome` for the tiering and the two rules that keep it honest
(key on the RETURNED status, and only on the winning transition).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.time import business_today
from app.models.vendor_portal import MilestoneRespondResponse
from app.services.milestone_email_service import send_milestone_pm_alert_email
from app.services.milestone_notification_service import (
    fetch_milestone_owner,
    notify_milestone_completed,
    notify_milestone_delayed,
)

logger = logging.getLogger(__name__)


def _has_pt_code(err: APIError, pt: str) -> bool:
    """True when the RPC raised SQLSTATE `pt` (e.g. 'PT409').

    Mirrors milestone_service: supabase-py surfaces the raised SQLSTATE on
    APIError.code, but we also scan the stringified error as a backstop.
    """
    code = str(getattr(err, "code", "") or "")
    return code == pt or pt in str(err)


def _map_rpc_error(err: APIError) -> HTTPException:
    """Translate an fn_record_milestone_response SQLSTATE into HTTP.

    PT409 (stale cycle / illegal action / milestone terminal) → 410 so the SPA
    lands on the "no longer current" page. PT404 → 404, PT422 → 422.
    """
    if _has_pt_code(err, "PT409"):
        return HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This check-in is no longer current",
        )
    if _has_pt_code(err, "PT404"):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check-in not found",
        )
    if _has_pt_code(err, "PT422"):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The check-in response was rejected",
        )
    logger.error("Unexpected fn_record_milestone_response failure: %s", err)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Failed to record the check-in response",
    )


async def _notify_pm_of_outcome(
    db: Client,
    email_service: Any,
    *,
    milestone_id: UUID | str,
    status_: str | None,
) -> None:
    """Tell the owning PM what the vendor's answer did to the milestone.

    Keyed on the status the RPC RETURNED, never on the vendor's button: the
    (status, action) → target mapping lives in transition_milestone(), and if it
    ever changes, this stays correct without being touched.

    The locked comms tiering — do not widen it here:

        delayed       → PM email + in-app
        completed     → in-app only (a finish is good news, not an interrupt)
        unresponsive  → PM email + in-app, but sent by the no-response JOB
        anything else → silence (an affirmative start/progress answer is not news)

    Every send is best-effort and independently guarded. By the time we get here
    the response row is written, the transition has happened and the token is
    spent; a dead mail provider must not turn that into an error for the vendor,
    and a failed email must not cost the PM the in-app alert too.
    """
    if status_ == "delayed":
        # Resolved here (rather than left to the notify helper, which does its
        # own lookup) because the email takes an explicit recipient. No owner =
        # nobody to address it to, so the email is skipped; the in-app helper
        # independently no-ops for the same reason.
        owner = fetch_milestone_owner(db, milestone_id)
        if owner is not None:
            try:
                await send_milestone_pm_alert_email(
                    milestone_id=milestone_id,
                    alert_type="delay",
                    recipient_user_id=owner["created_by"],
                    db=db,
                    email_service=email_service,
                )
            except Exception:  # noqa: BLE001 — never fail a committed response
                logger.error(
                    "milestone response: PM delay email raised for milestone %s",
                    milestone_id,
                    exc_info=True,
                )
        try:
            notify_milestone_delayed(db, milestone_id)
        except Exception:  # noqa: BLE001
            logger.error(
                "milestone response: in-app delay notify raised for milestone %s",
                milestone_id,
                exc_info=True,
            )

    elif status_ == "completed":
        try:
            notify_milestone_completed(db, milestone_id)
        except Exception:  # noqa: BLE001
            logger.error(
                "milestone response: in-app completion notify raised for milestone %s",
                milestone_id,
                exc_info=True,
            )


async def record_response(
    db: Client,
    *,
    milestone_alert_id: UUID | str,
    value: str,
    vendor_contact_id: UUID | str,
    milestone_id: UUID | str,
    email_service: Any,
) -> MilestoneRespondResponse:
    """Record a vendor's Yes/No check-in answer via the authoritative RPC.

    `vendor_contact_id` and `milestone_id` come from the milestone JWT, never
    the request body. Business-timezone today is passed in so actual start/end
    dates match the rest of the system's clock (America/Chicago), not the DB
    session tz.

    On the WINNING transition only, notifies the owning PM (see
    `_notify_pm_of_outcome`). `email_service` and `milestone_id` are required
    rather than optional so a future caller cannot quietly reintroduce the silent
    path this function exists to close.
    """
    try:
        resp = db.rpc(
            "fn_record_milestone_response",
            {
                "p_milestone_alert_id": str(milestone_alert_id),
                "p_response_value": value,
                "p_vendor_contact_id": str(vendor_contact_id),
                "p_today": business_today().isoformat(),
            },
        ).execute()
    except APIError as exc:
        raise _map_rpc_error(exc) from exc

    data = resp.data
    row = data[0] if isinstance(data, list) and data else data
    if not row:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to record the check-in response",
        )

    result = MilestoneRespondResponse(
        outcome=row["outcome"],
        recorded_value=row["recorded_value"],
        recorded_at=row["recorded_at"],
        milestone_status=row["milestone_status"],
    )

    # Winning transition ONLY. 'already_answered' also carries a real
    # milestone_status (the RPC re-reads it on the UNIQUE path), so gating on
    # the status alone would let a scanner double-click notify the PM twice.
    if result.outcome == "recorded":
        await _notify_pm_of_outcome(
            db,
            email_service,
            milestone_id=milestone_id,
            status_=result.milestone_status,
        )

    return result
