"""Standard budget template maintenance (Phase 2 · Task 2.1). Admin only.

One standard layout is the starting point for every project budget. Lines are
COPIED into budget_lines when a budget is created, so editing the template here
never changes an existing budget ("template changes apply to new budgets only").

Activity rows (bid_activity / internal_tm) are ordering slots: they decide where
a matching task sits and under which heading; they never become lines by
themselves (activity lines only exist as tasks).
"""

from __future__ import annotations

from postgrest.exceptions import APIError
from supabase import Client

from app.models.budgets import TemplateLineCreate, TemplateLineUpdate
from app.services.financial_errors import (
    FinancialError,
    first,
    money,
    to_financial_error,
)

_GENERIC = "The template could not be saved. Please try again."


def get_template(db: Client, template_id: str) -> dict:
    resp = db.table("budget_templates").select("*").eq("id", str(template_id)).maybe_single().execute()
    row = resp.data if resp else None
    if not row or row.get("deleted_at"):
        raise FinancialError(404, "Budget template not found")
    return row


def get_default_template(db: Client) -> dict:
    rows = (
        db.table("budget_templates").select("*")
        .eq("is_default", True).eq("is_active", True).is_("deleted_at", "null")
        .limit(1).execute()
    ).data or []
    if not rows:
        raise FinancialError(404, "No default budget template exists yet.")
    return rows[0]


def _lines(db: Client, template_id: str) -> list[dict]:
    return (
        db.table("budget_template_lines").select("*")
        .eq("budget_template_id", str(template_id)).order("sort_order").execute()
    ).data or []


def _get_line(db: Client, line_id: str) -> dict:
    resp = db.table("budget_template_lines").select("*").eq("id", str(line_id)).maybe_single().execute()
    row = resp.data if resp else None
    if not row:
        raise FinancialError(404, "Template line not found")
    return row


def add_line(db: Client, *, template_id: str, payload: TemplateLineCreate) -> dict:
    get_template(db, template_id)
    lines = _lines(db, template_id)
    if payload.line_type == "contingency" and any(
        ln["line_type"] == "contingency" and ln.get("is_active", True) for ln in lines
    ):
        raise FinancialError(409, "The template already has a contingency line.")
    row = {
        "budget_template_id": str(template_id),
        "line_type": payload.line_type,
        "line_subtype": payload.line_subtype,
        "name": payload.name,
        "section_name": payload.section_name,
        "trade_id": str(payload.trade_id) if payload.trade_id else None,
        "sort_order": max([ln["sort_order"] for ln in lines] or [0]) + 10,
        "default_amount": money(payload.default_amount),
        "default_payment_terms_days": payload.default_payment_terms_days,
        "default_cash_bucket": payload.default_cash_bucket,
    }
    try:
        resp = db.table("budget_template_lines").insert(row).execute()
    except APIError as exc:
        raise to_financial_error(exc, _GENERIC) from exc
    return first(resp.data) or row


def update_line(db: Client, *, line_id: str, payload: TemplateLineUpdate) -> dict:
    line = _get_line(db, line_id)
    get_template(db, line["budget_template_id"])
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return line
    row = {}
    for key, value in changes.items():
        if key == "default_amount":
            row[key] = money(value)
        elif key == "trade_id":
            row[key] = str(value) if value else None
        else:
            row[key] = value
    try:
        resp = db.table("budget_template_lines").update(row).eq("id", str(line_id)).execute()
    except APIError as exc:
        raise to_financial_error(exc, _GENERIC) from exc
    return first(resp.data) or {**line, **row}


def delete_line(db: Client, *, line_id: str) -> None:
    """Hard delete is safe: budget_lines.template_line_id is ON DELETE SET NULL
    and existing budgets keep their copied lines."""
    line = _get_line(db, line_id)
    get_template(db, line["budget_template_id"])
    try:
        db.table("budget_template_lines").delete().eq("id", str(line_id)).execute()
    except APIError as exc:
        raise to_financial_error(exc, _GENERIC) from exc


def reorder_lines(db: Client, *, template_id: str, line_ids: list) -> list[dict]:
    get_template(db, template_id)
    lines = _lines(db, template_id)
    known = {str(ln["id"]) for ln in lines}
    wanted = [str(x) for x in line_ids]
    if set(wanted) != known or len(wanted) != len(known):
        raise FinancialError(422, "Reorder must list every line of the template exactly once.")
    current = {str(ln["id"]): ln["sort_order"] for ln in lines}
    try:
        for index, line_id in enumerate(wanted, start=1):
            if current[line_id] != index * 10:
                db.table("budget_template_lines").update({"sort_order": index * 10}).eq("id", line_id).execute()
    except APIError as exc:
        raise to_financial_error(exc, _GENERIC) from exc
    return _lines(db, template_id)
