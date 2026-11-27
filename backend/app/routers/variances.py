"""Variance endpoints (Phase 4) — /api/v1/variances, /budget-lines/{id}/variances

  * read ........................ any active user
  * create ...................... field manager, project manager or admin
  * edit / cancel ............... the creator, a project manager or admin (before approval)
  * approve for payment / reject  field manager, project manager, executive or admin,
                                  never the creator; above the limit a manager too
                                  (all re-checked in SQL)
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.core.auth import get_current_active_user, require_roles
from app.core.supabase_client import get_supabase
from app.models.variances import VarianceCreate, VarianceNote, VarianceReject, VarianceUpdate
from app.services import financial_health_service, payment_notifications, variance_notifications, variance_service
from app.services.email_service import EmailService, get_email_service
from app.services.financial_errors import FinancialError

router = APIRouter()


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/variances")
async def list_variances(
    project_id: UUID | None = None,
    line_id: UUID | None = None,
    trade_id: UUID | None = None,
    variance_status: Literal["pending_approval", "approved", "rejected", "cancelled"] | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Variances, filtered by project, parent line, trade and status."""
    return await run_in_threadpool(
        lambda: variance_service.list_variances(
            db, user,
            project_id=str(project_id) if project_id else None,
            line_id=str(line_id) if line_id else None,
            trade_id=str(trade_id) if trade_id else None,
            status=variance_status,
        )
    )


@router.get("/variances/{variance_id}")
async def get_variance(
    variance_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """One variance with its history of estimates, edits and approvals."""
    try:
        return await run_in_threadpool(variance_service.detail, db, str(variance_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/budget-lines/{line_id}/variances", status_code=status.HTTP_201_CREATED)
async def create_variance(
    line_id: UUID,
    payload: VarianceCreate,
    user: dict = Depends(require_roles(*variance_service.CREATE_ROLES)),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Create a variance under a line; the same amount leaves contingency."""
    try:
        row = await run_in_threadpool(
            lambda: variance_service.create(db, line_id=str(line_id), payload=payload, actor_id=user["user_id"])
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await financial_health_service.after_change(db, row["project_id"], email_service)
    await variance_notifications.submitted(db, variance=row, actor=user)
    return row


@router.patch("/variances/{variance_id}")
async def update_variance(
    variance_id: UUID,
    payload: VarianceUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Edit before approval. The difference returns to or leaves contingency."""
    try:
        row = await run_in_threadpool(
            lambda: variance_service.update(db, variance_id=str(variance_id), payload=payload, user=user)
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await financial_health_service.after_change(db, row["project_id"], email_service)
    await variance_notifications.submitted(db, variance=row, actor=user)
    return row


@router.post("/variances/{variance_id}/cancel")
async def cancel_variance(
    variance_id: UUID,
    payload: VarianceNote,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cancel before approval; the whole amount returns to contingency."""
    try:
        row = await run_in_threadpool(
            lambda: variance_service.cancel(db, variance_id=str(variance_id), note=payload.note, user=user)
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await financial_health_service.after_change(db, row["project_id"])
    return row


@router.post("/variances/{variance_id}/approve")
async def approve_variance(
    variance_id: UUID,
    payload: VarianceNote,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Approve for payment, independent of the bid line."""
    try:
        row = await run_in_threadpool(
            lambda: variance_service.approve(
                db, variance_id=str(variance_id), note=payload.note, user=user,
                work_confirmed=payload.confirm_work_complete,
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    row, payment = row
    await financial_health_service.after_change(db, row["project_id"], email_service)
    # Routing, PO, trade / land team / finance emails: the payment engine's.
    await payment_notifications.after_step(db, email_service, pa=payment, actor=user)
    if row["status"] == "approved":
        await variance_notifications.decided(db, email_service, variance=row, actor=user)
    return row


@router.post("/variances/{variance_id}/reject")
async def reject_variance(
    variance_id: UUID,
    payload: VarianceReject,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Send a variance back with a reason."""
    try:
        row = await run_in_threadpool(
            lambda: variance_service.reject(
                db, variance_id=str(variance_id), reason=payload.reason, actor_id=user["user_id"],
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await financial_health_service.after_change(db, row["project_id"], email_service)
    await variance_notifications.decided(db, email_service, variance=row, actor=user)
    return row
