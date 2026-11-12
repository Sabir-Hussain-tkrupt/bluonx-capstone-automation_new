"""Internal invoice intake (Phase 2 · Task 2.6).

Field managers, office staff (PMs / admins) and finance upload invoices for
internal T&M lines (e.g. the attorney) into the private finance-documents
bucket, then categorise each one to a line. Categorising starts the payment
approval workflow (pending requests — the approve / route / reject actions are
Phase 6) and, when the invoice is above the line's remaining allowance on a
baselined budget, turns the overage into a variance funded from contingency.
All of that is ONE stored procedure (fn_categorise_internal_invoice).

Visibility: internal_invoices is finance-restricted under RLS. The list here is
served by FastAPI so non-finance uploaders still see the invoices THEY uploaded:
finance / executive / admin see all, everyone else only their own.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import user_has_any_role
from app.core.storage import (
    delete_file,
    get_signed_url,
    unique_object_path,
    upload_file,
)
from app.models.internal_invoices import InvoiceUpdate
from app.services.financial_errors import (
    FinancialError,
    call_rpc,
    first,
    money,
    to_financial_error,
)

logger = logging.getLogger(__name__)

FINANCE_BUCKET = "finance-documents"
_SEE_ALL = ("finance", "executive")


def can_see_all(user: dict) -> bool:
    return user_has_any_role(user, *_SEE_ALL)


def _project(db: Client, project_id: str) -> dict:
    resp = (
        db.table("projects").select("id, budget_status, status, archived_at, deleted_at")
        .eq("id", str(project_id)).maybe_single().execute()
    )
    row = resp.data if resp else None
    if not row or row.get("deleted_at"):
        raise FinancialError(404, "Project not found")
    return row


def get_invoice(db: Client, invoice_id: str, user: dict) -> dict:
    resp = db.table("internal_invoices").select("*").eq("id", str(invoice_id)).maybe_single().execute()
    row = resp.data if resp else None
    if not row or row.get("deleted_at"):
        raise FinancialError(404, "Invoice not found")
    if not can_see_all(user) and str(row["uploaded_by"]) != str(user["user_id"]):
        raise FinancialError(404, "Invoice not found")
    return row


def _enrich(db: Client, rows: list[dict]) -> list[dict]:
    """Attach line, uploader and vendor names (three small lookups, not N+1)."""
    if not rows:
        return rows

    def names(table: str, ids: set, col: str) -> dict:
        ids = {str(i) for i in ids if i}
        if not ids:
            return {}
        data = db.table(table).select(f"id, {col}").in_("id", list(ids)).execute().data or []
        return {str(r["id"]): r.get(col) for r in data}

    lines = names("budget_lines", {r.get("budget_line_id") for r in rows}, "name")
    users = names("users", {r.get("uploaded_by") for r in rows}, "full_name")
    vendors = names("vendors", {r.get("vendor_id") for r in rows}, "company_name")
    for r in rows:
        r["budget_line_name"] = lines.get(str(r.get("budget_line_id")))
        r["uploaded_by_name"] = users.get(str(r.get("uploaded_by")))
        r["vendor_name"] = vendors.get(str(r.get("vendor_id")))
    return rows


def list_invoices(db: Client, project_id: str, user: dict) -> list[dict]:
    _project(db, project_id)
    query = (
        db.table("internal_invoices").select("*")
        .eq("project_id", str(project_id)).is_("deleted_at", "null")
    )
    if not can_see_all(user):
        query = query.eq("uploaded_by", str(user["user_id"]))
    rows = query.order("created_at", desc=True).execute().data or []
    return _enrich(db, rows)


def create_invoice(
    db: Client,
    *,
    project_id: str,
    user: dict,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    amount: Decimal,
    payee_name: str | None,
    vendor_id: str | None,
    invoice_number: str | None,
    invoice_date: date | None,
    notes: str | None,
) -> dict:
    project = _project(db, project_id)
    if project.get("archived_at"):
        raise FinancialError(409, "This project is archived.")
    if amount is None or amount <= 0:
        raise FinancialError(422, "The invoice amount must be greater than zero.")
    if amount.as_tuple().exponent < -2:
        raise FinancialError(422, "Amounts can have at most 2 decimal places.")
    if not (payee_name or "").strip() and not vendor_id:
        raise FinancialError(422, "Enter the payee or choose a vendor.")

    storage_path = unique_object_path(f"{project_id}/invoices", filename)
    upload_file(db, FINANCE_BUCKET, storage_path, file_bytes, content_type)

    row = {
        "project_id": str(project_id),
        "vendor_id": str(vendor_id) if vendor_id else None,
        "payee_name": (payee_name or "").strip() or None,
        "invoice_number": (invoice_number or "").strip() or None,
        "invoice_date": invoice_date.isoformat() if invoice_date else None,
        "amount": money(amount),
        "file_path": storage_path,
        "file_name": filename,
        "file_size": len(file_bytes),
        "status": "received",
        "notes": (notes or "").strip() or None,
        "uploaded_by": str(user["user_id"]),
    }
    try:
        resp = db.table("internal_invoices").insert(row).execute()
    except APIError as exc:
        delete_file(db, FINANCE_BUCKET, storage_path)
        raise to_financial_error(exc, "The invoice could not be saved.") from exc
    created = first(resp.data)
    if not created:
        delete_file(db, FINANCE_BUCKET, storage_path)
        raise FinancialError(500, "The invoice could not be saved.")
    return _enrich(db, [created])[0]


def update_invoice(db: Client, *, invoice_id: str, payload: InvoiceUpdate, user: dict) -> dict:
    invoice = get_invoice(db, invoice_id, user)
    if invoice["status"] != "received":
        raise FinancialError(409, "Only invoices that are not yet categorised can be edited.")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _enrich(db, [invoice])[0]
    row = {}
    for key, value in changes.items():
        if key == "amount":
            row[key] = money(value)
        elif key == "invoice_date":
            row[key] = value.isoformat() if value else None
        elif key == "vendor_id":
            row[key] = str(value) if value else None
        else:
            row[key] = value
    try:
        resp = db.table("internal_invoices").update(row).eq("id", str(invoice_id)).execute()
    except APIError as exc:
        raise to_financial_error(exc, "The invoice could not be saved.") from exc
    return _enrich(db, [first(resp.data) or {**invoice, **row}])[0]


def categorise_invoice(db: Client, *, invoice_id: str, line_id: str, user: dict) -> dict:
    get_invoice(db, invoice_id, user)
    data = call_rpc(
        db, "fn_categorise_internal_invoice",
        {"p_invoice_id": str(invoice_id), "p_line_id": str(line_id), "p_actor": str(user["user_id"])},
        "The invoice could not be categorised. Please try again.",
    )
    if not isinstance(data, dict):
        data = first(data) or {}
    return data


def cancel_invoice(db: Client, *, invoice_id: str, user: dict) -> dict:
    invoice = get_invoice(db, invoice_id, user)
    if invoice["status"] not in ("received", "categorised"):
        raise FinancialError(
            409, "This invoice is already in payment approval and can no longer be cancelled here."
        )
    resp = db.table("internal_invoices").update({"status": "cancelled"}).eq("id", str(invoice_id)).execute()
    return _enrich(db, [first(resp.data) or {**invoice, "status": "cancelled"}])[0]


def signed_url(db: Client, *, invoice_id: str, user: dict) -> str:
    invoice = get_invoice(db, invoice_id, user)
    return get_signed_url(db, FINANCE_BUCKET, invoice["file_path"])
