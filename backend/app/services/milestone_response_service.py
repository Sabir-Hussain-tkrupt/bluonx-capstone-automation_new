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
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.time import business_today
from app.models.vendor_portal import MilestoneRespondResponse

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


def record_response(
    db: Client,
    *,
    milestone_alert_id: UUID | str,
    value: str,
    vendor_contact_id: UUID | str,
) -> MilestoneRespondResponse:
    """Record a vendor's Yes/No check-in answer via the authoritative RPC.

    `vendor_contact_id` comes from the milestone JWT, never the request body.
    Business-timezone today is passed in so actual start/end dates match the
    rest of the system's clock (America/Chicago), not the DB session tz.
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

    return MilestoneRespondResponse(
        outcome=row["outcome"],
        recorded_value=row["recorded_value"],
        recorded_at=row["recorded_at"],
        milestone_status=row["milestone_status"],
    )
