"""Variance lines (Phase 4 · Module 4).

The money rules live in the database (migration 20261125): creating a variance
deducts contingency, editing moves the difference, approving opens its own
payment approval, and approved variances are frozen. This module checks the
request, calls the procedures and reads v_variances / variance_events.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from supabase import Client

from app.core.auth import user_has_any_role
from app.services.budget_service import _ensure_editable, get_line, get_project
from app.services.financial_errors import FinancialError, call_rpc, first, money

CREATE_ROLES = ("field_manager", "project_manager")
MANAGER_ROLES = ("project_manager", "executive")
APPROVE_ROLES = ("field_manager", *MANAGER_ROLES)
_PAGE = 1000

EVENT_LABELS = {
    "created": "Created",
    "amount_changed": "Amount changed",
    "details_changed": "Details changed",
    "resubmitted": "Resubmitted",
    "routed_to_manager": "First approval, sent to a manager",
    "approved": "Approved for payment",
    "rejected": "Rejected",
    "cancelled": "Cancelled",
}


def permissions(row: dict, user: dict) -> dict[str, Any]:
    """What this user may do now. The procedures re-check all of it."""
    uid = str(user["user_id"])
    creator = uid == str(row["created_by"])
    manager = user_has_any_role(user, *MANAGER_ROLES)
    open_ = row["status"] in ("draft", "pending_approval", "rejected")
    editor = creator or user_has_any_role(user, "project_manager")
    pending = row["status"] == "pending_approval"
    second = row["payment_status"] == "awaiting_manager"
    routed_here = second and uid == str(row.get("routed_to_user_id"))
    reviewer = routed_here or user_has_any_role(user, *APPROVE_ROLES)

    # Phase 6: the payment engine's rules decide (the database re-checks them).
    from app.services import payment_rules as rules

    stage = "pending" if row["payment_status"] in ("not_requested", "pending") else row["payment_status"]
    actor = rules.Approver(
        id=uid, roles=frozenset(set(user.get("roles") or []) | {user.get("role")}) - {None},
        is_employee=user.get("is_employee", True) is not False,
    )
    decision = rules.decide(
        rules.Payment(
            status=stage, gross=Decimal(str(row.get("amount") or 0)),
            field_approved_by=str(row["field_approved_by"]) if row.get("field_approved_by") else None,
            routed_to=str(row["routed_to_user_id"]) if row.get("routed_to_user_id") else None,
            variance_created_by=str(row["created_by"]),
        ),
        actor, rules.Policy(),
    )
    blocked = None if decision.allowed or not pending else decision.reason
    return {
        "can_edit": open_ and editor,
        "can_cancel": open_ and editor and not row.get("internal_invoice_id"),
        "can_approve": pending and blocked is None,
        "can_reject": pending and not creator and reviewer and actor.is_employee,
        "approve_blocked_reason": blocked,
        # Phase 6: the first approval also confirms the work is complete.
        "needs_work_confirmation": pending and row["payment_status"] in ("not_requested", "pending"),
    }


def list_variances(
    db: Client, user: dict, *, project_id: str | None = None, line_id: str | None = None,
    trade_id: str | None = None, status: str | None = None,
) -> list[dict]:
    trade_ids: list[str] = []
    if trade_id:
        # A trade also matches its subtrades, like the other trade filters.
        subs = db.table("trades").select("id").eq("parent_trade_id", trade_id).execute().data or []
        trade_ids = [trade_id, *[str(s["id"]) for s in subs]]
    rows: list[dict] = []
    while True:
        q = db.table("v_variances").select("*")
        if project_id:
            q = q.eq("project_id", project_id)
        if line_id:
            q = q.eq("parent_budget_line_id", line_id)
        if trade_ids:
            q = q.in_("trade_id", trade_ids)
        if status:
            q = q.eq("status", status)
        batch = (
            q.order("created_at", desc=True).order("id").range(len(rows), len(rows) + _PAGE - 1).execute()
        ).data or []
        rows.extend(batch)
        if len(batch) < _PAGE:
            break
    return [{**r, "permissions": permissions(r, user)} for r in rows]


def get_variance(db: Client, variance_id: str) -> dict:
    resp = db.table("v_variances").select("*").eq("id", variance_id).maybe_single().execute()
    if not resp or not resp.data:
        raise FinancialError(404, "Variance not found")
    return resp.data


def detail(db: Client, variance_id: str, user: dict) -> dict:
    row = get_variance(db, variance_id)
    events = (
        db.table("variance_events").select("*").eq("variance_id", variance_id).order("event_no").execute()
    ).data or []
    ids = list({str(e["actor_user_id"]) for e in events})
    users = db.table("users").select("id, full_name, email").in_("id", ids).execute().data or [] if ids else []
    names = {str(u["id"]): u.get("full_name") or u.get("email") for u in users}
    return {
        **row,
        "permissions": permissions(row, user),
        "history": [
            {
                **e,
                "label": EVENT_LABELS.get(e["event_type"], e["event_type"]),
                "actor_name": names.get(str(e["actor_user_id"])),
            }
            for e in events
        ],
    }


def _check_trade(db: Client, trade_id: Any) -> None:
    rows = db.table("trades").select("id, is_active").eq("id", str(trade_id)).execute().data or []
    if not rows or not rows[0].get("is_active"):
        raise FinancialError(422, "The selected trade does not exist or is inactive.")


def _check_vendor(db: Client, vendor_id: Any) -> None:
    rows = (
        db.table("vendors").select("id").eq("id", str(vendor_id)).is_("deleted_at", "null").execute()
    ).data or []
    if not rows:
        raise FinancialError(422, "The selected vendor does not exist.")


def create(db: Client, *, line_id: str, payload, actor_id: str) -> dict:
    line = get_line(db, line_id)
    project = get_project(db, line["project_id"])
    _ensure_editable(project)
    if project.get("budget_status") != "baselined":
        raise FinancialError(422, "Baseline the budget first: until then, change the line's amount instead.")
    if line["line_type"] in ("contingency", "variance", "land") or line.get("line_subtype") == "unallocated":
        raise FinancialError(422, "A variance cannot be created under this line.")
    _check_trade(db, payload.trade_id)
    vendor_id = payload.vendor_id
    if vendor_id:
        _check_vendor(db, vendor_id)
    elif line.get("award_id"):
        award = db.table("awards").select("vendor_id").eq("id", line["award_id"]).maybe_single().execute()
        vendor_id = (award.data or {}).get("vendor_id") if award else None
    created = first(call_rpc(
        db, "fn_create_variance",
        {
            "p_parent_line_id": str(line_id), "p_description": payload.description,
            "p_amount": money(payload.amount), "p_actor": str(actor_id),
            "p_trade_id": str(payload.trade_id), "p_vendor_id": str(vendor_id) if vendor_id else None,
        },
        "The variance could not be created. Please try again.",
    ))
    if not created:
        raise FinancialError(500, "The variance could not be created. Please try again.")
    return get_variance(db, str(created["id"]))


def _editable(db: Client, variance_id: str, user: dict) -> dict:
    row = get_variance(db, variance_id)
    _ensure_editable(get_project(db, row["project_id"]))
    if row["status"] in ("approved", "cancelled"):
        raise FinancialError(
            422, f"This variance is {row['status']} and can no longer be changed. Create a new variance instead."
        )
    if not permissions(row, user)["can_edit"]:
        raise FinancialError(403, "Only the person who created this variance, a project manager or an admin can change it.")
    return row


def update(db: Client, *, variance_id: str, payload, user: dict) -> dict:
    row = _editable(db, variance_id, user)
    changes = payload.model_dump(exclude_unset=True)
    trade = changes.get("trade_id", row["trade_id"])
    vendor = changes.get("vendor_id", row["vendor_id"])
    if trade and str(trade) != str(row["trade_id"]):
        _check_trade(db, trade)
    if vendor and str(vendor) != str(row["vendor_id"]):
        _check_vendor(db, vendor)
    call_rpc(
        db, "fn_edit_variance",
        {
            "p_variance_id": variance_id,
            "p_amount": money(changes.get("amount", row["amount"])),
            "p_description": changes.get("description", row["description"]),
            "p_trade_id": str(trade) if trade else None,
            "p_vendor_id": str(vendor) if vendor else None,
            "p_actor": str(user["user_id"]),
            "p_reason": (changes.get("reason") or "").strip() or None,
        },
        "The variance could not be saved. Please try again.",
    )
    return get_variance(db, variance_id)


def cancel(db: Client, *, variance_id: str, note: str | None, user: dict) -> dict:
    _editable(db, variance_id, user)
    call_rpc(
        db, "fn_adjust_variance",
        {
            "p_variance_id": variance_id, "p_new_amount": "0", "p_actor": str(user["user_id"]),
            "p_reason": (note or "").strip() or None,
        },
        "The variance could not be cancelled. Please try again.",
    )
    return get_variance(db, variance_id)


def approve(db: Client, *, variance_id: str, note: str | None, user: dict, work_confirmed: bool) -> tuple[dict, dict]:
    """Approve for payment through the Phase 6 payment engine (limits, external
    field managers, executive threshold). Returns (variance, payment)."""
    from app.services import payment_service

    _ensure_editable(get_project(db, get_variance(db, variance_id)["project_id"]))
    out = payment_service.for_variance(
        db, variance_id=variance_id, user=user, note=note, work_confirmed=work_confirmed,
    )
    return get_variance(db, variance_id), out["payment"]


def reject(db: Client, *, variance_id: str, reason: str, actor_id: str) -> dict:
    _ensure_editable(get_project(db, get_variance(db, variance_id)["project_id"]))
    call_rpc(
        db, "fn_reject_variance",
        {"p_variance_id": variance_id, "p_actor": str(actor_id), "p_reason": reason},
        "The variance could not be rejected. Please try again.",
    )
    return get_variance(db, variance_id)
