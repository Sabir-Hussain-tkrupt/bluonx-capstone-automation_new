"""
Milestone management write path (Phase 10.1).

The first real writer to `milestones`. It owns PM-driven creation, edits, deletion,
and the manual start/complete/reschedule overrides. Automated email/token/scheduler
transitions arrive in Phase 10.2/10.3 — every status change here funnels through the
single `_apply_status` seam so 10.3 can swap the body for a `transition_milestone()`
RPC without touching the router.

Contract gate: a milestone requires the task's active contract. We resolve `contract_id`
server-side with the SAME predicate as the partial unique index
`idx_contracts_one_active_per_task` (status <> 'terminated'), which guarantees at most one
such row. The client never supplies contract_id.

Writes are single-statement supabase-py ops (mirror contract_service / bid_templates); the
DB trigger `fn_enforce_milestone_task_consistency` and NOT NULL FKs are the integrity
backstop, not the gate.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)


class MilestoneError(Exception):
    """Raised on milestone-write failure; the router maps it to an HTTPException.
    Mirrors AwardError / ContractError."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Transition rules (action → resulting status + allowed source statuses) ──
#
# Two actions land on `in_progress` (start, reschedule) but from different source
# sets, so the map is keyed by ACTION, not by target status.
_ACTION_TARGET_STATUS: dict[str, str] = {
    "start": "in_progress",
    "complete": "completed",
    "reschedule": "in_progress",
}

_ACTION_ALLOWED_FROM: dict[str, set[str]] = {
    "start": {"scheduled"},
    "complete": {"scheduled", "in_progress", "delayed", "unresponsive"},
    "reschedule": {"in_progress", "delayed", "unresponsive"},
}


# ── Pure functions (no DB — unit-tested directly) ───────────────────────────


def validate_date_order(start: date, end: date) -> None:
    """Reject an end-before-start window. Same-day (end == start) is allowed."""
    if end < start:
        raise MilestoneError(
            422, "Milestone end date cannot be before its start date."
        )


def assert_transition_allowed(current: str, action: str) -> None:
    """Guard a manual status change. `action` is one of start/complete/reschedule."""
    allowed = _ACTION_ALLOWED_FROM.get(action)
    if allowed is None:
        raise MilestoneError(422, f"Unknown milestone action: {action!r}")
    if current not in allowed:
        target = _ACTION_TARGET_STATUS[action]
        raise MilestoneError(
            409,
            f"Cannot {action} a milestone in '{current}' status "
            f"(would move it to '{target}').",
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


def _is_fk_violation(err: APIError) -> bool:
    """Postgres 23503 (foreign_key_violation) — a child row (milestone_responses /
    milestone_alerts) still references this milestone."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23503" or "foreign key" in msg


def _resolve_active_contract_id(db: Client, task_id: str) -> str:
    """Return the task's single active contract id, or raise 422.

    # NOTE: lenient gate — allows milestones while a contract is still
    # 'sent_for_signature'. To require a SIGNED contract, filter
    # status IN ('executed','active') here (and in the frontend
    # useTaskActiveContract query). See the plan FLIP POINT.
    """
    resp = (
        db.table("contracts")
        .select("id")
        .eq("task_id", str(task_id))
        .neq("status", "terminated")
        .limit(1)
        .execute()
    )
    row = _first(resp.data)
    if not row:
        raise MilestoneError(
            422,
            "Task has no active contract; a contract must exist before "
            "milestones can be added.",
        )
    return row["id"]


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
    """Create a milestone for the task's active contract (Phase 10.1).

    Resolves contract_id server-side (contract gate), validates the date window,
    computes the next sort_order, and inserts at status 'scheduled'.
    """
    contract_id = _resolve_active_contract_id(db, str(payload.task_id))
    validate_date_order(payload.start_date, payload.end_date)
    sort_order = next_sort_order(_existing_sort_orders(db, str(payload.task_id)))

    insert_row = {
        "task_id": str(payload.task_id),
        "contract_id": contract_id,
        "name": payload.name,
        "start_date": _date_str(payload.start_date),
        "end_date": _date_str(payload.end_date),
        "notes": payload.notes,
        "sort_order": sort_order,
        "status": "scheduled",
        "created_by": str(created_by),
    }
    try:
        resp = db.table("milestones").insert(insert_row).execute()
    except APIError as exc:
        logger.error("Supabase insert failed for milestones: %s", exc)
        raise MilestoneError(
            422, f"Database rejected the milestone: {exc.message}"
        ) from exc

    row = _first(resp.data)
    if not row:
        raise MilestoneError(500, "Milestone creation failed.")
    return row


def update_milestone(milestone_id: str, payload, *, db: Client) -> dict:
    """Patch mutable fields (name/dates/notes/sort_order). No status change here."""
    current = _get_milestone_or_404(db, milestone_id)

    update_data = payload.model_dump(exclude_unset=True)

    # If the resulting window has both endpoints defined, re-validate order.
    new_start = update_data.get("start_date", current.get("start_date"))
    new_end = update_data.get("end_date", current.get("end_date"))
    if new_start is not None and new_end is not None:
        validate_date_order(_as_date(new_start), _as_date(new_end))

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
        logger.error("Supabase update failed for milestones: %s", exc)
        raise MilestoneError(
            422, f"Database rejected the update: {exc.message}"
        ) from exc

    return _first(resp.data) or current


def delete_milestone(milestone_id: str, *, db: Client) -> None:
    """Delete a milestone. Blocked (409) when child rows reference it."""
    _get_milestone_or_404(db, milestone_id)
    try:
        db.table("milestones").delete().eq("id", str(milestone_id)).execute()
    except APIError as exc:
        if _is_fk_violation(exc):
            raise MilestoneError(
                409, "Milestone has recorded activity and cannot be deleted."
            ) from exc
        logger.error("Supabase delete failed for milestones: %s", exc)
        raise MilestoneError(
            422, f"Failed to delete milestone: {exc.message}"
        ) from exc


def _apply_status(
    milestone_id: str,
    action: str,
    *,
    db: Client,
    actual_start_date: date | None = None,
    actual_end_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """The SINGLE funnel for every milestone status change.

    Loads the row, guards the transition, then writes the new status plus any
    provided actual/planned dates in one update.

    # SWAP POINT (10.3): the body below becomes a call to the transition_milestone()
    # RPC (server-authoritative transitions + token bookkeeping).
    """
    current = _get_milestone_or_404(db, milestone_id)
    assert_transition_allowed(current["status"], action)

    target_status = _ACTION_TARGET_STATUS[action]
    update_data: dict[str, Any] = {"status": target_status}

    if actual_start_date is not None:
        update_data["actual_start_date"] = _date_str(actual_start_date)
    if actual_end_date is not None:
        # Completion sanity: don't let actual completion predate actual start.
        known_start = actual_start_date or _as_date(current.get("actual_start_date"))
        if known_start is not None and actual_end_date < known_start:
            raise MilestoneError(
                422, "Actual end date cannot be before the actual start date."
            )
        update_data["actual_end_date"] = _date_str(actual_end_date)
    if end_date is not None:
        update_data["end_date"] = _date_str(end_date)

    try:
        resp = (
            db.table("milestones")
            .update(update_data)
            .eq("id", str(milestone_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase status update failed for milestones: %s", exc)
        raise MilestoneError(
            422, f"Database rejected the status change: {exc.message}"
        ) from exc

    return _first(resp.data) or {**current, **update_data}


def mark_started(
    milestone_id: str, *, actual_start_date: date | None = None, db: Client
) -> dict:
    """Manual start override → in_progress. Defaults actual_start_date to today."""
    return _apply_status(
        milestone_id,
        "start",
        db=db,
        actual_start_date=actual_start_date or date.today(),
    )


def mark_completed(
    milestone_id: str, *, actual_end_date: date | None = None, db: Client
) -> dict:
    """Manual completion override → completed. Defaults actual_end_date to today."""
    return _apply_status(
        milestone_id,
        "complete",
        db=db,
        actual_end_date=actual_end_date or date.today(),
    )


def reschedule(milestone_id: str, *, end_date: date, db: Client) -> dict:
    """Push the planned end date out and return the milestone to in_progress.

    # NO-OP until 10.3: rescheduling should also restart the check-in cycle and
    # invalidate any outstanding response tokens. Not implemented in 10.1.
    """
    return _apply_status(milestone_id, "reschedule", db=db, end_date=end_date)


def _as_date(value: Any) -> date | None:
    """Coerce a date | ISO-string | None into a date for comparisons."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
