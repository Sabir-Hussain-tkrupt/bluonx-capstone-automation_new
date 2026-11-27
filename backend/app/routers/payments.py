"""Payment approvals and finance hand-off (Phase 6) — /api/v1/payment-approvals,
/budget-lines/{id}/payments, /finance-handoffs, /users/approval-settings

  * read approvals ........................ any active user
  * request, confirm, approve, reject ..... decided by payment_rules (and SQL)
  * hand-off log and exports .............. finance, executive or admin
  * approver settings per user ............ admin
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import get_current_active_user, require_admin, require_roles
from app.core.storage import get_signed_url
from app.core.supabase_client import get_supabase
from app.models.payments import (
    ApproverSettingsUpdate,
    MarkExported,
    PaymentApprove,
    PaymentNote,
    PaymentReject,
    PaymentRequest,
)
from app.services import finance_exports, financial_health_service, payment_notifications, payment_service as svc
from app.services.contingency_service import get_settings
from app.services.email_service import EmailService, get_email_service
from app.services.financial_errors import FinancialError, to_financial_error

router = APIRouter()
_finance = require_roles("finance", "executive")


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _after(db: Client, email_service: EmailService, pa: dict, user: dict) -> None:
    await payment_notifications.after_step(db, email_service, pa=pa, actor=user)
    if pa["status"] == "approved":
        await financial_health_service.after_change(db, pa["project_id"], email_service)


# ── Approvals ───────────────────────────────────────────────────────────────


@router.get("/payment-approvals")
async def list_payment_approvals(
    scope: Literal["queue", "pending", "rejected", "sent", "all"] = "queue",
    project_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """queue = what you can approve now; pending / rejected / sent = everyone's."""
    return await run_in_threadpool(
        lambda: svc.list_payments(db, user, scope=scope, project_id=str(project_id) if project_id else None)
    )


@router.get("/payment-approvals/{payment_id}")
async def get_payment_approval(
    payment_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    try:
        return await run_in_threadpool(svc.detail, db, str(payment_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.get("/budget-lines/{line_id}/payments")
async def line_payments(
    line_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """What can be paid on the line: remaining, retainage held, history."""
    try:
        return await run_in_threadpool(svc.line_options, db, str(line_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/budget-lines/{line_id}/payments", status_code=201)
async def request_payment(
    line_id: UUID,
    payload: PaymentRequest,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Full, progress or retainage release; optionally confirm the work at once."""
    try:
        out = await run_in_threadpool(
            lambda: svc.request(
                db, line_id=str(line_id), user=user, kind=payload.payment_kind, percent=payload.progress_percent,
                note=payload.note, confirm_now=payload.confirm_work_complete,
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await _after(db, email_service, out["payment"], user)
    return out["payment"]


@router.post("/payment-approvals/{payment_id}/approve")
async def approve_payment(
    payment_id: UUID,
    payload: PaymentApprove,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    try:
        out = await run_in_threadpool(
            lambda: svc.approve(db, payment_id=str(payment_id), user=user, note=payload.note,
                                work_confirmed=payload.confirm_work_complete)
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await _after(db, email_service, out["payment"], user)
    return out["payment"]


@router.post("/payment-approvals/{payment_id}/reject")
async def reject_payment(
    payment_id: UUID,
    payload: PaymentReject,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Back to the field manager. The trade is not told."""
    try:
        pa = await run_in_threadpool(lambda: svc.reject(db, payment_id=str(payment_id), user=user, reason=payload.reason))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _after(db, email_service, pa, user)
    return pa


@router.post("/payment-approvals/{payment_id}/resubmit")
async def resubmit_payment(
    payment_id: UUID,
    payload: PaymentNote,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    try:
        return await run_in_threadpool(lambda: svc.resubmit(db, payment_id=str(payment_id), user=user, note=payload.note))
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/payment-approvals/{payment_id}/cancel")
async def cancel_payment(
    payment_id: UUID,
    payload: PaymentNote,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    try:
        return await run_in_threadpool(lambda: svc.cancel(db, payment_id=str(payment_id), user=user, note=payload.note))
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Finance hand-off ────────────────────────────────────────────────────────


def _handoffs(db: Client, only_pending: bool, project_id: str | None) -> list[dict]:
    rows: list[dict] = []
    while True:
        q = db.table("v_finance_handoffs").select("*")
        if only_pending:
            q = q.is_("exported_at", "null")
        if project_id:
            q = q.eq("project_id", project_id)
        batch = (q.order("created_at", desc=True).order("id").range(len(rows), len(rows) + 499).execute()).data or []
        rows.extend(batch)
        if len(batch) < 500:
            return rows


@router.get("/finance-handoffs")
async def list_handoffs(
    only_pending: bool = False,
    project_id: UUID | None = None,
    user: dict = Depends(_finance),
    db: Client = Depends(get_supabase),
):
    """Hand-off log: each PO with its email_log delivery status."""
    return await run_in_threadpool(_handoffs, db, only_pending, str(project_id) if project_id else None)


@router.get("/finance-handoffs/export")
async def export_handoffs(
    format: Literal["csv", "xlsx", "quickbooks"] = "xlsx",
    only_pending: bool = True,
    user: dict = Depends(_finance),
    db: Client = Depends(get_supabase),
):
    """pending = not yet marked as exported. QuickBooks = Bills import CSV."""
    rows = await run_in_threadpool(_handoffs, db, only_pending, None)
    stamp = datetime.now(timezone.utc).date().isoformat()
    if format == "xlsx":
        body, media, name = finance_exports.to_xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"finance-handoffs-{stamp}.xlsx"
    elif format == "quickbooks":
        account = str((await run_in_threadpool(get_settings, db)).get("quickbooks_expense_account") or "Job Expenses")
        body, media, name = finance_exports.to_quickbooks(rows, account), "text/csv; charset=utf-8", f"quickbooks-bills-{stamp}.csv"
    else:
        body, media, name = finance_exports.to_csv(rows), "text/csv; charset=utf-8", f"finance-handoffs-{stamp}.csv"
    return Response(content=body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/finance-handoffs/mark-exported")
async def mark_exported(
    payload: MarkExported,
    user: dict = Depends(_finance),
    db: Client = Depends(get_supabase),
):
    ids = [str(i) for i in payload.handoff_ids]
    try:
        resp = await run_in_threadpool(lambda: db.table("finance_handoffs").update(
            {"exported_at": datetime.now(timezone.utc).isoformat()}).in_("id", ids).is_("exported_at", "null").execute())
    except APIError as exc:
        raise _http(to_financial_error(exc, "The hand-offs could not be marked as exported.")) from exc
    return {"updated": len(resp.data or [])}


@router.post("/finance-handoffs/{handoff_id}/resend")
async def resend_handoff(
    handoff_id: UUID,
    user: dict = Depends(_finance),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    ok = await payment_notifications.deliver_handoff(db, email_service, handoff_id=str(handoff_id))
    if not ok:
        raise HTTPException(status_code=502, detail="The hand-off email could not be sent. Check the finance recipients.")
    return {"sent": True}


@router.get("/finance-handoffs/{handoff_id}/document")
async def handoff_document(
    handoff_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Signed link to the PO PDF."""
    resp = await run_in_threadpool(
        lambda: db.table("finance_handoffs").select("document_path").eq("id", str(handoff_id)).maybe_single().execute())
    path = ((resp.data if resp else None) or {}).get("document_path")
    if not path:
        raise HTTPException(status_code=404, detail="The PO document is not ready yet.")
    return {"url": await run_in_threadpool(get_signed_url, db, payment_notifications.FINANCE_BUCKET, path)}


# ── Approver settings per user ──────────────────────────────────────────────


@router.get("/approval-settings")
async def list_approver_settings(
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Limit, reports-to manager, backup approver and away date of every user."""
    return await run_in_threadpool(svc.approver_settings, db)


@router.put("/users/{user_id}/approval-settings")
async def update_approver_settings(
    user_id: UUID,
    payload: ApproverSettingsUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
    _: str | None = Query(default=None, include_in_schema=False),
):
    try:
        await run_in_threadpool(lambda: svc.update_approver_settings(
            db, user_id=str(user_id), changes=payload.model_dump(exclude_unset=True), actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    rows = await run_in_threadpool(svc.approver_settings, db)
    return next((r for r in rows if r["id"] == str(user_id)), None)
