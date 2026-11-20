"""Contingency engine endpoints (Phase 3) — /api/v1/projects/{id}/contingency,
/projects/{id}/bidding, /contingency-top-ups, /financial-settings/contingency

Who may do what (the backend check is the real gate; these handlers hold the
service_role key, which bypasses RLS):
  * read the panel / ledger, export ........ any active user
  * set the project contingency % .......... admin (draft budgets only)
  * request a top-up ....................... project manager or admin
  * approve / reject a top-up .............. executive only (also checked in SQL)
  * mark bidding complete .................. project manager or admin
  * reopen bidding, contingency settings ... admin
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from supabase import Client

from app.core.auth import get_current_active_user, require_admin, require_roles
from app.core.supabase_client import get_supabase
from app.models.contingency import (
    BiddingCompleteRequest,
    ContingencyPercentUpdate,
    ContingencySettingsUpdate,
    TopUpDecision,
    TopUpRequestCreate,
)
from app.services import contingency_notifications, contingency_service
from app.services.email_service import EmailService, get_email_service
from app.services.financial_errors import FinancialError

router = APIRouter()


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# ── Panel and ledger ────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/contingency")
async def get_contingency(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Contingency panel: amount, % of the base, buckets, top-ups, checkpoint."""
    try:
        return await run_in_threadpool(contingency_service.overview, db, str(project_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.get("/projects/{project_id}/contingency/ledger")
async def get_ledger(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Every contingency movement with the running balance overall and per bucket."""
    try:
        contingency_service._project(db, str(project_id))
        return await run_in_threadpool(contingency_service.build_ledger, db, str(project_id))
    except FinancialError as exc:
        raise _http(exc) from exc


@router.get("/projects/{project_id}/contingency/ledger/export")
async def export_ledger(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Download the ledger as CSV."""
    try:
        filename, content = await run_in_threadpool(contingency_service.ledger_csv, db, str(project_id))
    except FinancialError as exc:
        raise _http(exc) from exc
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/projects/{project_id}/contingency/percent")
async def set_contingency_percent(
    project_id: UUID,
    payload: ContingencyPercentUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Set the project contingency % (admin). A draft budget is recalculated at
    once; after baseline the % is fixed and only a top-up adds money."""
    try:
        return await run_in_threadpool(
            lambda: contingency_service.set_percent(
                db, project_id=str(project_id), percent=payload.contingency_percent, actor_id=user["user_id"],
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Bidding-complete checkpoint ─────────────────────────────────────────────


@router.get("/projects/{project_id}/bidding/checkpoint")
async def bidding_checkpoint(
    project_id: UUID,
    user: dict = Depends(require_roles("project_manager")),
    db: Client = Depends(get_supabase),
):
    """What marking bidding complete would show: tasks without an award, the
    contingency left and whether it would escalate."""
    try:
        return await run_in_threadpool(contingency_service.checkpoint_preview, db, str(project_id))
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/projects/{project_id}/bidding/complete")
async def complete_bidding(
    project_id: UUID,
    payload: BiddingCompleteRequest,
    user: dict = Depends(require_roles("project_manager")),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Mark bidding complete (project manager or admin). Far below target
    escalates to the executives and finance."""
    try:
        result = await run_in_threadpool(
            lambda: contingency_service.complete_bidding(
                db, project_id=str(project_id), note=payload.note,
                acknowledge=payload.acknowledge_open_tasks, actor_id=user["user_id"],
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await contingency_notifications.bidding_completed(
        db, email_service, project_id=str(project_id), result=result, actor=user,
    )
    return result


@router.post("/projects/{project_id}/bidding/reopen")
async def reopen_bidding(
    project_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Undo "bidding complete" (admin)."""
    try:
        return await run_in_threadpool(
            lambda: contingency_service.reopen_bidding(db, project_id=str(project_id), actor_id=user["user_id"])
        )
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Top-ups ─────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/contingency/top-ups", status_code=status.HTTP_201_CREATED)
async def request_top_up(
    project_id: UUID,
    payload: TopUpRequestCreate,
    user: dict = Depends(require_roles("project_manager")),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Ask for more contingency (amount + reason). Executives are notified."""
    try:
        bucket = await run_in_threadpool(
            lambda: contingency_service.request_top_up(
                db, project_id=str(project_id), amount=payload.amount, reason=payload.reason,
                actor_id=user["user_id"],
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await contingency_notifications.top_up_requested(db, email_service, bucket=bucket, requester=user)
    return bucket


@router.post("/contingency-top-ups/{bucket_id}/decision")
async def decide_top_up(
    bucket_id: UUID,
    payload: TopUpDecision,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Approve or reject a top-up (executives only). Approval adds the amount to
    contingency and to the total budget; finance and sales are emailed."""
    if not contingency_service.is_executive(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an executive can approve or reject a contingency top-up.")
    try:
        bucket = await run_in_threadpool(
            lambda: contingency_service.decide_top_up(
                db, bucket_id=str(bucket_id), approve=payload.approve, approved_amount=payload.approved_amount,
                note=payload.note, actor_id=user["user_id"],
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    await contingency_notifications.top_up_decided(db, email_service, bucket=bucket, approver=user)
    return bucket


@router.post("/contingency-top-ups/{bucket_id}/cancel")
async def cancel_top_up(
    bucket_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Withdraw a pending top-up request (the requester or an admin)."""
    try:
        return await run_in_threadpool(
            lambda: contingency_service.cancel_top_up(db, bucket_id=str(bucket_id), user=user)
        )
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Organisation settings ───────────────────────────────────────────────────


@router.get("/financial-settings/contingency")
async def get_contingency_settings(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Default contingency %, bidding target / escalation %, finance and sales emails."""
    return await run_in_threadpool(contingency_service.get_settings, db)


@router.put("/financial-settings/contingency")
async def update_contingency_settings(
    payload: ContingencySettingsUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Change the contingency settings (admin)."""
    changes = payload.model_dump(exclude_none=True)
    target = changes.get("bidding_target_contingency_percent")
    escalation = changes.get("bidding_escalation_percent")
    if target is not None and escalation is not None and escalation > target:
        raise HTTPException(status_code=422, detail="The escalation % must not be above the target %.")
    return await run_in_threadpool(contingency_service.update_settings, db, changes, user["user_id"])
