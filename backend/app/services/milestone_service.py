"""
Milestone management write path (Phase 10 foundation).

Owns PM-driven creation, edits, and the manual start/complete/reschedule/cancel
transitions. There is no hard delete: the milestone_events ledger is append-only
(deleting a milestone would cascade into its immutable creation event and be
blocked), so a mistaken milestone is retired via cancel, not removed. Every status change funnels through ONE authoritative writer,
the `transition_milestone()` RPC: a single transaction under a row lock that applies
the status + dates and writes one immutable `milestone_events` row. Creation is the
same story via `fn_create_milestone()` (row + opening event, atomic). No application
SQL writes `milestones.status` anymore, and no Python code decides transition legality
— the RPC's transition table is the sole authority (10.2 vendor responses and 10.3 the
scheduler reuse the same RPC).

Contract gate: a milestone requires the task's active contract. We resolve `contract_id`
server-side with the SAME predicate as the partial unique index
`idx_contracts_one_active_per_task` (status <> 'terminated'), which guarantees at most one
such row. The client never supplies contract_id.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.core.time import business_today

logger = logging.getLogger(__name__)


class MilestoneError(Exception):
    """Raised on milestone-write failure; the router maps it to an HTTPException.
    Mirrors AwardError / ContractError."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── RPC action names (transition_milestone p_action) ─────────────────────────
#
# The RPC derives the target status + trigger_type from the action and owns all
# legality. PM actions always carry the acting user's id as p_actor_user_id.
_ACTION_MARK_STARTED = "pm_mark_started"
_ACTION_MARK_COMPLETED = "pm_mark_completed"
_ACTION_RESCHEDULE = "pm_reschedule"
_ACTION_CANCEL = "pm_cancel"
# Scheduler action — no actor. Legal only from scheduled/in_progress.
_ACTION_SYSTEM_NO_RESPONSE = "system_no_response"


# ── Pure functions (no DB — unit-tested directly) ───────────────────────────


def validate_date_order(start: date, end: date) -> None:
    """Reject an end-before-start window. Same-day (end == start) is allowed."""
    if end < start:
        raise MilestoneError(
            422, "Milestone end date cannot be before its start date."
        )


def validate_not_past(start: date) -> None:
    """Reject a start date before today.

    A past start suppresses the start_check (the daily job fires it only when
    start_date == today), so the milestone never leaves 'scheduled' via the
    normal vendor path — every later check-in the vendor answers is illegal from
    'scheduled' and rolls back. Requiring start >= today keeps the lifecycle
    reachable; combined with validate_date_order (end >= start) it also forbids a
    past end date. Business-timezone today; DB business clock is America/Chicago.
    """
    today = business_today()
    if start < today:
        raise MilestoneError(
            422,
            f"Start date ({start.isoformat()}) cannot be in the past "
            f"(today is {today.isoformat()}).",
        )


def next_sort_order(existing_orders: list[int]) -> int:
    """Next append position: max(existing) + 1, or 0 when there are none."""
    return max(existing_orders, default=-1) + 1


# ── DB helpers ──────────────────────────────────────────────────────────────


def _first(data: Any) -> dict | None:
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _has_pt_code(err: APIError, pt: str) -> bool:
    """True when the RPC raised SQLSTATE `pt` (e.g. 'PT409').

    supabase-py surfaces a raised SQLSTATE on APIError.code (mirrors the 23505/23503
    heuristic in contract_service), but we also scan the stringified error as a
    backstop in case a given client version tucks it into the message instead.
    """
    code = str(getattr(err, "code", "") or "")
    return code == pt or pt in str(err)


def _err_message(err: APIError) -> str | None:
    msg = getattr(err, "message", None)
    return str(msg) if msg else None


def _map_transition_error(err: APIError) -> MilestoneError:
    """Translate a `transition_milestone` SQLSTATE into a MilestoneError.

    PT404 → 404, PT409 → 409 (illegal action for the current status, or a date
    write blocked by the guard trigger), PT422 → 422 (date validation / bad args).
    Anything else is unexpected → 502.
    """
    if _has_pt_code(err, "PT404"):
        return MilestoneError(404, "Milestone not found")
    if _has_pt_code(err, "PT409"):
        return MilestoneError(
            409, "That action isn't allowed for the milestone's current status."
        )
    if _has_pt_code(err, "PT422"):
        return MilestoneError(
            422, _err_message(err) or "The milestone update was rejected."
        )
    logger.error("Unexpected milestone RPC failure: %s", err)
    return MilestoneError(502, "Milestone update failed.")


def _resolve_active_contract_id(db: Client, task_id: str) -> str:
    """Return the task's single active contract id, or raise.

    A milestone requires a live contract. `completed` and `terminated` are dead
    ends: a completed contract has already passed the fn_mark_contract_complete
    gate (all milestones closed), so a new one would silently void it; a
    terminated one is gone. Both are rejected with 409 naming the state. A task
    with no contract at all is 422 (nothing exists yet to attach to).

    # NOTE: lenient gate — allows milestones while a contract is still
    # 'sent_for_signature'. To require a SIGNED contract, keep only
    # status IN ('executed','active') as `active` below (and mirror it in the
    # frontend useTaskActiveContract query). See the plan FLIP POINT.
    """
    resp = (
        db.table("contracts")
        .select("id, status")
        .eq("task_id", str(task_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise MilestoneError(
            422,
            "Task has no active contract; a contract must exist before "
            "milestones can be added.",
        )
    # idx_contracts_one_active_per_task guarantees at most one non-terminated
    # contract, so this picks the single live/completed one when it exists.
    active = next((r for r in rows if r["status"] != "terminated"), None)
    if active is None:
        raise MilestoneError(
            409,
            "This task's contract is terminated; milestones cannot be added.",
        )
    if active["status"] == "completed":
        raise MilestoneError(
            409,
            "This task's contract is completed; milestones cannot be added.",
        )
    return active["id"]


def _get_milestone_or_404(db: Client, milestone_id: str) -> dict:
    """Load a milestone row or raise 404 (PGRST116 = 0 rows from .single())."""
    try:
        resp = (
            db.table("milestones")
            .select("*")
            .eq("id", str(milestone_id))
            .single()
            .execute()
        )
    except APIError as exc:
        if "PGRST116" in str(getattr(exc, "code", "")) or "0 rows" in str(
            getattr(exc, "message", "")
        ):
            raise MilestoneError(404, "Milestone not found") from exc
        logger.error("Supabase query failed for milestones: %s", exc)
        raise MilestoneError(502, "Failed to fetch milestone from database") from exc

    if not resp.data:
        raise MilestoneError(404, "Milestone not found")
    return resp.data


def _milestone_has_rows(db: Client, table: str, milestone_id: str) -> bool:
    """True when any row in `table` references this milestone (activity check)."""
    resp = (
        db.table(table)
        .select("id")
        .eq("milestone_id", str(milestone_id))
        .limit(1)
        .execute()
    )
    return _first(resp.data) is not None


def _existing_sort_orders(db: Client, task_id: str) -> list[int]:
    resp = (
        db.table("milestones")
        .select("sort_order")
        .eq("task_id", str(task_id))
        .execute()
    )
    return [r["sort_order"] for r in (resp.data or []) if r.get("sort_order") is not None]


def _date_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


# ── DB write functions ──────────────────────────────────────────────────────


def create_milestone(payload, *, created_by: str, db: Client) -> dict:
    """Create a milestone for the task's active contract.

    Resolves contract_id server-side (contract gate rejects completed/terminated),
    validates the date window (end >= start, start not in the past), computes the
    next sort_order, then calls `fn_create_milestone` so the row and its opening
    `creation` ledger event are written atomically. `baseline_end_date` is frozen
    to `end_date` by the RPC.
    """
    contract_id = _resolve_active_contract_id(db, str(payload.task_id))
    validate_date_order(payload.start_date, payload.end_date)
    validate_not_past(payload.start_date)
    sort_order = next_sort_order(_existing_sort_orders(db, str(payload.task_id)))

    try:
        resp = db.rpc(
            "fn_create_milestone",
            {
                "p_task_id": str(payload.task_id),
                "p_contract_id": str(contract_id),
                "p_name": payload.name,
                "p_start_date": _date_str(payload.start_date),
                "p_end_date": _date_str(payload.end_date),
                "p_notes": payload.notes,
                "p_sort_order": sort_order,
                "p_created_by": str(created_by),
            },
        ).execute()
    except APIError as exc:
        logger.error("fn_create_milestone failed: %s", exc)
        raise MilestoneError(
            422, f"Database rejected the milestone: {exc.message}"
        ) from exc

    row = _first(resp.data)
    if not row:
        raise MilestoneError(500, "Milestone creation failed.")
    return row


def update_milestone(milestone_id: str, payload, *, db: Client) -> dict:
    """Patch mutable fields. name/notes/sort_order are always editable; dates are
    editable ONLY while the milestone is still `scheduled` and unannounced.

    Once the milestone is live (status left `scheduled`, or a `milestone_alerts`
    row exists) date fields are rejected here — moving a live end date is a
    reschedule and must go through the RPC so it bumps cycle_number and records a
    ledger event. Status is never changed here.
    """
    current = _get_milestone_or_404(db, milestone_id)

    update_data = payload.model_dump(exclude_unset=True)
    changing_dates = "start_date" in update_data or "end_date" in update_data

    if changing_dates:
        is_live = current["status"] != "scheduled" or _milestone_has_rows(
            db, "milestone_alerts", milestone_id
        )
        if is_live:
            raise MilestoneError(
                409,
                "Dates are locked once the milestone is live. "
                "Use Reschedule to move the end date.",
            )
        # Still schedulable: re-validate the window before writing.
        new_start = update_data.get("start_date", current.get("start_date"))
        new_end = update_data.get("end_date", current.get("end_date"))
        if new_start is not None and new_end is not None:
            validate_date_order(_as_date(new_start), _as_date(new_end))
        # Moving the start into the past would strand it in 'scheduled' the same
        # way a past start on create would, so guard the Edit path too. Only when
        # start_date is actually being changed (a legacy past-start row may still
        # have its end/name edited).
        if "start_date" in update_data:
            validate_not_past(_as_date(update_data["start_date"]))

    if "start_date" in update_data:
        update_data["start_date"] = _date_str(update_data["start_date"])
    if "end_date" in update_data:
        update_data["end_date"] = _date_str(update_data["end_date"])

    if not update_data:
        return current

    try:
        resp = (
            db.table("milestones")
            .update(update_data)
            .eq("id", str(milestone_id))
            .execute()
        )
    except APIError as exc:
        # Backstop: the guard trigger raises PT409 if a live date edit slips past
        # the pre-check above (e.g. an alert landed between the read and write).
        if _has_pt_code(exc, "PT409"):
            raise MilestoneError(
                409,
                "Dates are locked once the milestone is live. "
                "Use Reschedule to move the end date.",
            ) from exc
        logger.error("Supabase update failed for milestones: %s", exc)
        raise MilestoneError(
            422, f"Database rejected the update: {exc.message}"
        ) from exc

    return _first(resp.data) or current


def _transition(
    milestone_id: str,
    *,
    action: str,
    actor_user_id: str,
    note: str,
    db: Client,
    actual_start_date: date | None = None,
    actual_end_date: date | None = None,
    new_end_date: date | None = None,
) -> dict:
    """The SINGLE funnel for every milestone status change.

    A thin wrapper over `transition_milestone()`: one atomic, row-locked RPC call
    that applies the status + dates and writes one immutable ledger row. The RPC
    owns all transition legality; this layer only shapes params and maps SQLSTATEs.
    """
    try:
        resp = db.rpc(
            "transition_milestone",
            {
                "p_milestone_id": str(milestone_id),
                "p_action": action,
                "p_actor_user_id": str(actor_user_id),
                "p_actor_vendor_contact_id": None,
                "p_milestone_response_id": None,
                "p_milestone_alert_id": None,
                "p_actual_start_date": _date_str(actual_start_date),
                "p_actual_end_date": _date_str(actual_end_date),
                "p_new_end_date": _date_str(new_end_date),
                "p_note": note,
            },
        ).execute()
    except APIError as exc:
        raise _map_transition_error(exc) from exc

    row = _first(resp.data)
    if not row:
        raise MilestoneError(500, "Milestone transition failed.")
    return row


def mark_started(
    milestone_id: str, *, actor_user_id: str, actual_start_date: date | None = None, db: Client
) -> dict:
    """Manual start override → in_progress. Defaults actual_start_date to today."""
    actual_start = actual_start_date or business_today()
    return _transition(
        milestone_id,
        action=_ACTION_MARK_STARTED,
        actor_user_id=actor_user_id,
        note=f"Marked started (actual start {actual_start.isoformat()})",
        db=db,
        actual_start_date=actual_start,
    )


def mark_completed(
    milestone_id: str, *, actor_user_id: str, actual_end_date: date | None = None, db: Client
) -> dict:
    """Manual completion override → completed. Defaults actual_end_date to today.

    Never invents an actual_start_date: completing a never-started milestone leaves
    actual_start_date NULL (an honest gap beats a fabricated start).
    """
    actual_end = actual_end_date or business_today()
    return _transition(
        milestone_id,
        action=_ACTION_MARK_COMPLETED,
        actor_user_id=actor_user_id,
        note=f"Marked completed (actual end {actual_end.isoformat()})",
        db=db,
        actual_end_date=actual_end,
    )


def reschedule(milestone_id: str, *, actor_user_id: str, end_date: date, db: Client) -> dict:
    """Push the planned end date out and return the milestone to in_progress.

    A reschedule bumps cycle_number in the RPC, staleness-killing every outstanding
    check-in token for this milestone. baseline_end_date is left untouched — the gap
    to the moved end_date IS the drift.

    Rejects a past end date here (422): the RPC's own guard only checks
    new_end < start_date, so a past-but-after-start date would pass and resume the
    milestone to in_progress with a finish that already elapsed. The date-vs-start
    check stays in the RPC (it defends any writer); this past-date rule only needs
    to hold on the one reachable path, and REVOKE makes the service that path.
    """
    today = business_today()
    if end_date < today:
        raise MilestoneError(
            422,
            f"New end date ({end_date.isoformat()}) is in the past "
            f"(today is {today.isoformat()}).",
        )
    return _transition(
        milestone_id,
        action=_ACTION_RESCHEDULE,
        actor_user_id=actor_user_id,
        note=f"Rescheduled end date to {_date_str(end_date)}",
        db=db,
        new_end_date=end_date,
    )


def cancel_milestone(milestone_id: str, *, actor_user_id: str, db: Client) -> dict:
    """Retire a milestone that has activity → cancelled. The correct alternative to
    delete once a milestone is live."""
    return _transition(
        milestone_id,
        action=_ACTION_CANCEL,
        actor_user_id=actor_user_id,
        note="Cancelled by PM",
        db=db,
    )


def escalate_no_response(
    milestone_id: str, *, milestone_alert_id: str, note: str, db: Client
) -> dict:
    """Scheduler-driven no-response escalation → unresponsive.

    Unlike the pm_* / vendor_* transitions this carries NO actor (the RPC's
    system_no_response path requires neither an actor_user_id nor a
    actor_vendor_contact_id) and pins the check-in alert whose silence triggered
    it. Legal only from scheduled/in_progress — the RPC raises PT409 otherwise,
    which the caller treats as "already moved, skip".
    """
    try:
        resp = db.rpc(
            "transition_milestone",
            {
                "p_milestone_id": str(milestone_id),
                "p_action": _ACTION_SYSTEM_NO_RESPONSE,
                "p_actor_user_id": None,
                "p_actor_vendor_contact_id": None,
                "p_milestone_response_id": None,
                "p_milestone_alert_id": str(milestone_alert_id),
                "p_actual_start_date": None,
                "p_actual_end_date": None,
                "p_new_end_date": None,
                "p_note": note,
            },
        ).execute()
    except APIError as exc:
        raise _map_transition_error(exc) from exc

    row = _first(resp.data)
    if not row:
        raise MilestoneError(500, "Milestone escalation failed.")
    return row


def _as_date(value: Any) -> date | None:
    """Coerce a date | ISO-string | None into a date for comparisons."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
