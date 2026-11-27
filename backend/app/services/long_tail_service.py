"""Long-tail items: escrows and property taxes (Phase 7 · Module 7).

The money rules live in the database (migration 20261128): every escrow has its
two cost lines (premium, repairs to city standard), every tax year is a budget
line, and their amounts move flat (template placeholder first, then
contingency). This module checks the request, calls the procedures and builds
the long-tail view.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import user_has_any_role
from app.core.storage import get_signed_url, unique_object_path, upload_file
from app.services.budget_service import _ensure_editable, get_project
from app.services.financial_errors import FinancialError, call_rpc, first, money, to_financial_error

FINANCE_BUCKET = "finance-documents"
OPEN_ESCROW = ("planned", "posted", "works_built", "inspection", "corrections", "signed_off")
EVENT_LABELS = {
    "created": "Escrow set up", "updated": "Details changed", "posted": "Posted", "works_built": "Works built",
    "inspection": "Inspection walk", "corrections": "Corrections", "signed_off": "Government sign-off",
    "released": "Released", "cancelled": "Cancelled", "bond_renewed": "Bond renewed",
    "defect_open": "Defect recorded", "defect_repaired": "Defect repaired", "defect_waived": "Defect waived",
}
NEXT_STEP = {
    "planned": ["posted", "cancelled"], "posted": ["works_built", "cancelled"], "works_built": ["inspection"],
    "inspection": ["corrections", "signed_off"], "corrections": ["inspection", "signed_off"],
    "signed_off": ["released"], "released": [], "cancelled": [],
}


def _d(v: Any) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else Decimal("0")


def permissions(user: dict) -> dict:
    return {
        "manage_escrows": user_has_any_role(user, "project_manager"),
        "record_works": user_has_any_role(user, "field_manager", "project_manager"),
        "manage_taxes": user_has_any_role(user, "project_manager", "finance"),
        "renew_bonds": user_has_any_role(user, "project_manager", "finance"),
    }


# ── Jurisdictions ───────────────────────────────────────────────────────────


def list_jurisdictions(db: Client) -> list[dict]:
    return (
        db.table("jurisdictions").select("*").is_("deleted_at", "null").order("name").execute()
    ).data or []


def save_jurisdiction(db: Client, *, jurisdiction_id: str | None, payload, actor_id: str) -> dict:
    row = payload.model_dump(mode="json")
    try:
        if jurisdiction_id:
            resp = db.table("jurisdictions").update(row).eq("id", jurisdiction_id).execute()
        else:
            resp = db.table("jurisdictions").insert({**row, "created_by": actor_id}).execute()
    except APIError as exc:
        raise to_financial_error(exc, "The city / county could not be saved.") from exc
    out = first(resp.data)
    if not out:
        raise FinancialError(404, "City / county not found")
    return out


# ── Escrows ─────────────────────────────────────────────────────────────────


def get_escrow(db: Client, escrow_id: str) -> dict:
    resp = db.table("v_escrows").select("*").eq("id", escrow_id).maybe_single().execute()
    if not resp or not resp.data:
        raise FinancialError(404, "Escrow not found")
    return resp.data


def escrow_detail(db: Client, escrow_id: str, user: dict) -> dict:
    e = get_escrow(db, escrow_id)
    defects = (
        db.table("escrow_defects").select("*").eq("escrow_id", escrow_id).order("created_at").execute()
    ).data or []
    events = (db.table("escrow_events").select("*").eq("escrow_id", escrow_id).order("event_no").execute()).data or []
    ids = list({str(x["actor_user_id"]) for x in events if x.get("actor_user_id")})
    users = db.table("users").select("id, full_name, email").in_("id", ids).execute().data or [] if ids else []
    names = {str(u["id"]): u.get("full_name") or u.get("email") for u in users}
    return {
        **e,
        "next_steps": NEXT_STEP.get(e["status"], []),
        "defects": defects,
        "history": [{**x, "label": EVENT_LABELS.get(x["event_type"], x["event_type"]),
                     "actor_name": names.get(str(x.get("actor_user_id")))} for x in events],
        "permissions": permissions(user),
    }


def save_escrow(db: Client, *, project_id: str, escrow_id: str | None, payload, actor_id: str) -> dict:
    _ensure_editable(get_project(db, project_id))
    data = payload.model_dump(mode="json")
    rows = call_rpc(
        db, "fn_save_escrow",
        {"p_project": project_id, "p_escrow_id": escrow_id, "p_actor": str(actor_id), "p_data": data},
        "The escrow could not be saved.",
    )
    row = first(rows)
    if not row:
        raise FinancialError(500, "The escrow could not be saved.")
    return get_escrow(db, str(row["id"]))


def _escrow_project(db: Client, escrow_id: str) -> dict:
    e = get_escrow(db, escrow_id)
    _ensure_editable(get_project(db, e["project_id"]))
    return e


def transition(db: Client, *, escrow_id: str, to: str, on: date | None, note: str | None, signoff_by: str | None,
               actor_id: str) -> dict:
    _escrow_project(db, escrow_id)
    call_rpc(
        db, "fn_escrow_transition",
        {"p_escrow_id": escrow_id, "p_actor": str(actor_id), "p_to": to, "p_date": on.isoformat() if on else None,
         "p_note": note, "p_signoff_by": signoff_by},
        "The escrow could not be updated.",
    )
    return get_escrow(db, escrow_id)


def save_defect(db: Client, *, escrow_id: str, defect_id: str | None, payload, actor_id: str) -> dict:
    _escrow_project(db, escrow_id)
    call_rpc(
        db, "fn_save_escrow_defect",
        {"p_escrow_id": escrow_id, "p_defect_id": defect_id, "p_actor": str(actor_id),
         "p_description": payload.description, "p_location": payload.location,
         "p_cost": money(payload.repair_cost), "p_status": payload.status},
        "The defect could not be saved.",
    )
    return get_escrow(db, escrow_id)


def renew_bond(db: Client, *, escrow_id: str, new_expiry: date, premium: Decimal, actor_id: str) -> dict:
    _escrow_project(db, escrow_id)
    call_rpc(
        db, "fn_renew_escrow_bond",
        {"p_escrow_id": escrow_id, "p_actor": str(actor_id), "p_new_expiry": new_expiry.isoformat(),
         "p_premium": money(premium)},
        "The renewal could not be saved.",
    )
    return get_escrow(db, escrow_id)


def upload_document(db: Client, *, escrow_id: str, filename: str, content_type: str, data: bytes) -> dict:
    e = _escrow_project(db, escrow_id)
    path = unique_object_path(f"{e['project_id']}/escrows/{escrow_id}", filename)
    upload_file(db, FINANCE_BUCKET, path, data, content_type)
    db.table("escrows").update({"document_path": path, "document_name": filename}).eq("id", escrow_id).execute()
    return get_escrow(db, escrow_id)


def document_url(db: Client, escrow_id: str) -> str:
    e = get_escrow(db, escrow_id)
    if not e.get("document_path"):
        raise FinancialError(404, "No bond document uploaded yet.")
    return get_signed_url(db, FINANCE_BUCKET, e["document_path"])


# ── Property taxes ──────────────────────────────────────────────────────────


def set_tax_year(db: Client, *, project_id: str, payload, actor_id: str) -> dict:
    _ensure_editable(get_project(db, project_id))
    return call_rpc(
        db, "fn_set_property_tax_year",
        {"p_project": project_id, "p_actor": str(actor_id), "p_year": payload.tax_year,
         "p_jurisdiction_id": str(payload.jurisdiction_id), "p_basis": payload.estimate_basis,
         "p_amount": money(payload.amount), "p_assessed": money(payload.assessed_value),
         "p_rate": money(payload.tax_rate_percent), "p_sold_percent": money(payload.sold_portion_percent or 0),
         "p_parcel": payload.parcel_reference},
        "The tax year could not be saved.",
    ) or {}


def update_tax(db: Client, *, tax_id: str, payload, actor_id: str) -> dict:
    resp = db.table("property_taxes").select("project_id").eq("id", tax_id).maybe_single().execute()
    if not resp or not resp.data:
        raise FinancialError(404, "Property tax not found")
    _ensure_editable(get_project(db, resp.data["project_id"]))
    changes = payload.model_dump(exclude_unset=True)
    current = db.table("property_taxes").select("actual_amount").eq("id", tax_id).maybe_single().execute()
    actual = changes["actual_amount"] if "actual_amount" in changes else ((current.data or {}).get("actual_amount"))
    call_rpc(
        db, "fn_update_property_tax",
        {"p_id": tax_id, "p_actor": str(actor_id), "p_estimated": money(changes.get("estimated_amount")),
         "p_actual": money(actual), "p_due": changes["due_date"].isoformat() if changes.get("due_date") else None,
         "p_status": changes.get("status"), "p_sold_percent": money(changes.get("sold_portion_percent"))},
        "The property tax could not be saved.",
    )
    return {"project_id": resp.data["project_id"]}


def set_sold_portion(db: Client, *, project_id: str, percent: Decimal, from_year: int | None, actor_id: str) -> int:
    _ensure_editable(get_project(db, project_id))
    return call_rpc(
        db, "fn_set_tax_sold_portion",
        {"p_project": project_id, "p_actor": str(actor_id), "p_percent": money(percent), "p_from_year": from_year},
        "The sold portion could not be saved.",
    ) or 0


# ── 7.5 Long-tail view ──────────────────────────────────────────────────────


def overview(db: Client, project_id: str, user: dict) -> dict:
    project = get_project(db, project_id)
    escrows = (
        db.table("v_escrows").select("*").eq("project_id", project_id).order("created_at").execute()
    ).data or []
    taxes = (
        db.table("v_property_taxes").select("*").eq("project_id", project_id)
        .order("tax_year").order("installment_number").execute()
    ).data or []
    cont = (
        db.table("budget_lines").select("budget_amount").eq("project_id", project_id)
        .eq("line_type", "contingency").is_("deleted_at", "null").limit(1).execute()
    ).data or []
    contingency = _d(cont[0]["budget_amount"]) if cont else Decimal("0")

    open_escrows = [e for e in escrows if e["status"] in OPEN_ESCROW]
    escrow_costs = sum((_d(e["premium_line_amount"]) + _d(e["repair_line_amount"]) for e in open_escrows), Decimal("0"))
    open_taxes = [t for t in taxes if t["status"] in ("estimated", "billed", "in_approval")]
    tax_open = sum((_d(t["amount_due"]) for t in open_taxes), Decimal("0"))
    horizon = (date.today() + timedelta(days=365)).isoformat()
    upcoming = [t for t in open_taxes if t.get("due_date") and str(t["due_date"]) <= horizon]
    reserve = project.get("long_tail_reserve_amount")
    reserve_d = _d(reserve) if reserve is not None else None
    return {
        "project_id": project_id,
        "budget_status": project.get("budget_status"),
        "escrows": escrows,
        "taxes": taxes,
        "upcoming_taxes": upcoming,
        "totals": {
            "open_escrows": len(open_escrows),
            "open_escrow_costs": money(escrow_costs),
            "open_taxes": money(tax_open),
            "long_tail_open": money(escrow_costs + tax_open),
            "cash_posted": money(sum((_d(e["secured_amount"]) for e in open_escrows
                                      if e["security_form"] == "cash" and e.get("posted_date")), Decimal("0"))),
            "reserve_required": money(reserve_d) if reserve_d is not None else None,
            "contingency": money(contingency),
            "below_reserve": reserve_d is not None and contingency < reserve_d,
            "tax_increase": money(sum((_d(t["increase"]) for t in taxes if t.get("increase") is not None), Decimal("0"))),
        },
        "permissions": permissions(user),
    }
