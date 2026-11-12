"""Project budget write path (Phase 2 · Tasks 2.2 – 2.4).

Authorization is the router's job (`require_admin` on every write — only admins
create and edit budgets, matching today's admin-only project budget rule). This
module owns the rules the database does not express and the error mapping.

What the database already guarantees (Phase 1 / Phase 2 migrations) and this
module therefore does NOT re-implement:
  * amounts change only through procedures once the budget is baselined
  * locked lines, the flat-budget total, the single contingency line
  * task ↔ line sync (trigger on tasks)
Those surface as PT409 / PT422 with human-readable messages, passed through.

Reads are not here: the frontend reads v_budget_lines / v_project_budget_summary
directly under RLS (same split as holidays and milestones).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.models.budgets import (
    BudgetLineCreate,
    BudgetLineUpdate,
    LandClosingCreate,
    LandClosingUpdate,
)
from app.services.financial_errors import (
    FinancialError,
    call_rpc,
    first,
    money,
    to_financial_error,
)

logger = logging.getLogger(__name__)

_GENERIC = "The budget could not be saved. Please try again."


# ── Loading / guards ────────────────────────────────────────────────────────


def get_project(db: Client, project_id: str) -> dict:
    resp = (
        db.table("projects")
        .select("id, name, status, budget_status, archived_at, deleted_at")
        .eq("id", str(project_id))
        .maybe_single()
        .execute()
    )
    row = resp.data if resp else None
    if not row or row.get("deleted_at"):
        raise FinancialError(404, "Project not found")
    return row


def _ensure_editable(project: dict) -> None:
    if project.get("archived_at"):
        raise FinancialError(409, "This project is archived. Unarchive it to change the budget.")


def _ensure_has_budget(project: dict) -> None:
    if project.get("budget_status", "none") == "none":
        raise FinancialError(409, "This project has no budget yet. Create one first.")


def get_line(db: Client, line_id: str) -> dict:
    resp = db.table("budget_lines").select("*").eq("id", str(line_id)).maybe_single().execute()
    row = resp.data if resp else None
    if not row or row.get("deleted_at"):
        raise FinancialError(404, "Budget line not found")
    return row


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


# ── Budget lifecycle ────────────────────────────────────────────────────────


def create_budget(
    db: Client, *, project_id: str, actor_id: str, template_id: str | None, contingency_percent
) -> list[dict]:
    """Template + every task → draft budget (fn_create_project_budget)."""
    project = get_project(db, project_id)
    _ensure_editable(project)
    if project.get("budget_status", "none") != "none":
        raise FinancialError(409, "This project already has a budget.")
    data = call_rpc(
        db,
        "fn_create_project_budget",
        {
            "p_project_id": str(project_id),
            "p_actor": str(actor_id),
            "p_template_id": str(template_id) if template_id else None,
            "p_contingency_percent": money(contingency_percent),
        },
        "The budget could not be created. Please try again.",
    )
    return data or []


def baseline_budget(db: Client, *, project_id: str, actor_id: str) -> dict:
    """Draft → baselined: estimates freeze, the total becomes flat."""
    project = get_project(db, project_id)
    _ensure_editable(project)
    _ensure_has_budget(project)
    data = call_rpc(
        db,
        "fn_baseline_project_budget",
        {"p_project_id": str(project_id), "p_actor": str(actor_id)},
        "The budget could not be baselined. Please try again.",
    )
    return first(data) or {}


# ── Lines ───────────────────────────────────────────────────────────────────


def add_line(db: Client, *, project_id: str, payload: BudgetLineCreate, actor_id: str) -> dict:
    """Add a line without a task (land, permit, impact fee, soft cost, long-tail,
    or an internal T&M portion such as engineering T&M)."""
    project = get_project(db, project_id)
    _ensure_editable(project)
    _ensure_has_budget(project)

    if project["budget_status"] == "baselined" and payload.budget_amount != 0:
        raise FinancialError(
            409,
            "The budget is baselined: new lines start at $0. Extra money is added "
            "through variances so the total budget stays flat.",
        )

    parent = None
    if payload.parent_line_id:
        parent = get_line(db, str(payload.parent_line_id))
        if str(parent["project_id"]) != str(project_id):
            raise FinancialError(422, "The parent line belongs to another project.")

    # Position: after the parent (T&M portion under its heading), else after the
    # last line of the same section, else just before contingency.
    lines = (
        db.table("budget_lines")
        .select("id, line_type, section_name, sort_order")
        .eq("project_id", str(project_id))
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    section = payload.section_name or (parent or {}).get("section_name")
    if parent:
        sort_order = int(parent["sort_order"]) + 1
    else:
        same = [ln["sort_order"] for ln in lines if section and ln.get("section_name") == section]
        cont = [ln["sort_order"] for ln in lines if ln["line_type"] == "contingency"]
        if same:
            sort_order = max(same) + 1
        elif cont:
            sort_order = min(cont) - 1
        else:
            sort_order = max([ln["sort_order"] for ln in lines] or [0]) + 10

    row = {
        "project_id": str(project_id),
        "line_type": payload.line_type,
        "line_subtype": payload.line_subtype,
        "name": payload.name,
        "description": payload.description,
        "section_name": section,
        "parent_line_id": str(payload.parent_line_id) if payload.parent_line_id else None,
        "sort_order": sort_order,
        "budget_amount": money(payload.budget_amount),
        "anticipated_start_date": _iso(payload.anticipated_start_date),
        "anticipated_end_date": _iso(payload.anticipated_end_date),
        "payment_terms_days": payload.payment_terms_days,
        "cash_bucket": payload.cash_bucket,
        "is_payment_exempt": payload.line_type == "land",
        "created_by": str(actor_id),
        "updated_by": str(actor_id),
    }
    try:
        resp = db.table("budget_lines").insert(row).execute()
    except APIError as exc:
        raise to_financial_error(exc, _GENERIC) from exc
    created = first(resp.data)
    if not created:
        raise FinancialError(500, _GENERIC)
    return created


def update_line(db: Client, *, line_id: str, payload: BudgetLineUpdate, actor_id: str) -> dict:
    """Edit amount (draft), dates, payment terms, cash bucket, heading, name."""
    line = get_line(db, line_id)
    project = get_project(db, line["project_id"])
    _ensure_editable(project)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return line

    if "name" in changes and line.get("task_id"):
        raise FinancialError(422, "This line's name follows its task. Rename the task instead.")
    if "budget_amount" in changes:
        if line["line_type"] == "variance":
            raise FinancialError(422, "Variance amounts are changed through the variance itself.")
        if project["budget_status"] == "baselined":
            raise FinancialError(
                409,
                "The budget is baselined: amounts change only through bids, variances "
                "and executive-approved top-ups.",
            )
        if line.get("is_locked"):
            raise FinancialError(409, "This line is locked because its contract is executed.")

    # Date pair must stay ordered after the merge.
    start = changes.get("anticipated_start_date", line.get("anticipated_start_date"))
    end = changes.get("anticipated_end_date", line.get("anticipated_end_date"))
    if start and end and str(_iso(end)) < str(_iso(start)):
        raise FinancialError(422, "The end date cannot be before the start date.")

    row = {k: (money(v) if k == "budget_amount" else _iso(v)) for k, v in changes.items()}
    row["updated_by"] = str(actor_id)
    try:
        resp = db.table("budget_lines").update(row).eq("id", str(line_id)).execute()
    except APIError as exc:
        raise to_financial_error(exc, _GENERIC) from exc
    return first(resp.data) or {**line, **row}


def remove_line(db: Client, *, line_id: str, actor_id: str) -> dict:
    line = get_line(db, line_id)
    _ensure_editable(get_project(db, line["project_id"]))
    data = call_rpc(
        db, "fn_remove_budget_line",
        {"p_line_id": str(line_id), "p_actor": str(actor_id)},
        "The line could not be removed. Please try again.",
    )
    return first(data) or {}


def reorder_lines(db: Client, *, project_id: str, line_ids: list, actor_id: str) -> list[dict]:
    project = get_project(db, project_id)
    _ensure_editable(project)
    _ensure_has_budget(project)
    return call_rpc(
        db, "fn_reorder_budget_lines",
        {"p_project_id": str(project_id), "p_line_ids": [str(x) for x in line_ids], "p_actor": str(actor_id)},
        "The lines could not be reordered. Please try again.",
    ) or []


# ── Land closings ───────────────────────────────────────────────────────────


def _land_line(db: Client, line_id: str) -> dict:
    line = get_line(db, line_id)
    if line["line_type"] != "land":
        raise FinancialError(422, "Phased closings belong to a land line.")
    _ensure_editable(get_project(db, line["project_id"]))
    return line


def add_closing(db: Client, *, line_id: str, payload: LandClosingCreate, actor_id: str) -> dict:
    line = _land_line(db, line_id)
    existing = (
        db.table("land_closings").select("closing_sequence").eq("budget_line_id", str(line_id)).execute()
    ).data or []
    sequence = max([c["closing_sequence"] for c in existing] or [0]) + 1
    row = {
        "project_id": str(line["project_id"]),
        "budget_line_id": str(line_id),
        "closing_sequence": sequence,
        "acres": money(payload.acres),
        "amount": money(payload.amount),
        "planned_closing_date": payload.planned_closing_date.isoformat(),
        "notes": payload.notes,
        "created_by": str(actor_id),
    }
    try:
        resp = db.table("land_closings").insert(row).execute()
    except APIError as exc:
        raise to_financial_error(exc, "The closing could not be saved.") from exc
    return first(resp.data) or row


def update_closing(db: Client, *, closing_id: str, payload: LandClosingUpdate) -> dict:
    resp = db.table("land_closings").select("*").eq("id", str(closing_id)).maybe_single().execute()
    closing = resp.data if resp else None
    if not closing:
        raise FinancialError(404, "Closing not found")
    _land_line(db, closing["budget_line_id"])
    if closing["status"] == "cancelled":
        raise FinancialError(409, "A cancelled closing cannot be changed.")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") == "closed" and not (changes.get("actual_closing_date") or closing.get("actual_closing_date")):
        raise FinancialError(422, "Enter the actual closing date to mark the closing as closed.")
    row = {k: (money(v) if k in ("amount", "acres") else _iso(v)) for k, v in changes.items()}
    if not row:
        return closing
    try:
        out = db.table("land_closings").update(row).eq("id", str(closing_id)).execute()
    except APIError as exc:
        raise to_financial_error(exc, "The closing could not be saved.") from exc
    return first(out.data) or {**closing, **row}
