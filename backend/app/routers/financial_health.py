"""Contingency health and financial alerts (Phase 5) — /api/v1/projects/{id}/financial-health,
/financial-alerts

  * read .................................. any active user
  * setup, groundbreaking, decide, lift ... project manager, executive or admin
                                            (decide / lift re-checked in SQL)
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.core.auth import get_current_active_user, require_roles
from app.core.supabase_client import get_supabase
from app.models.financial_health import AlertDecision, HealthSetupUpdate, HoldLift
from app.services import financial_alert_notifications as notify
from app.services import financial_health_service as svc
from app.services.email_service import EmailService, get_email_service
from app.services.financial_errors import FinancialError

router = APIRouter()
_manager = require_roles(*svc.MANAGER_ROLES)


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/projects/{project_id}/financial-health")
async def get_health(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Contingency left %, work left %, spent breakdown, reserve, live alerts."""
    try:
        return await run_in_threadpool(svc.overview, db, str(project_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.put("/projects/{project_id}/financial-health/setup")
async def update_setup(
    project_id: UUID,
    payload: HealthSetupUpdate,
    user: dict = Depends(_manager),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Project manager, field manager and long-tail reserve."""
    try:
        await run_in_threadpool(
            lambda: svc.update_setup(
                db, project_id=str(project_id), changes=payload.model_dump(exclude_unset=True),
                actor_id=user["user_id"],
            )
        )
        await svc.after_change(db, project_id, email_service)
        return await run_in_threadpool(svc.overview, db, str(project_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/projects/{project_id}/financial-health/groundbreaking")
async def record_groundbreaking(
    project_id: UUID,
    user: dict = Depends(_manager),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Freeze today's contingency as the denominator of contingency left %."""
    try:
        await run_in_threadpool(
            lambda: svc.record_groundbreaking(db, project_id=str(project_id), actor_id=user["user_id"])
        )
        await svc.after_change(db, project_id, email_service)
        return await run_in_threadpool(svc.overview, db, str(project_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/projects/{project_id}/financial-health/lift-hold")
async def lift_hold(
    project_id: UUID,
    payload: HoldLift,
    user: dict = Depends(_manager),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Lift the financial hold with a reason."""
    try:
        held = await run_in_threadpool(
            lambda: svc.list_alerts(db, project_id=str(project_id), status="on_hold")
        )
        await run_in_threadpool(
            lambda: svc.lift_hold(db, project_id=str(project_id), reason=payload.reason, actor_id=user["user_id"])
        )
        await svc.after_change(db, project_id, email_service)
        if held:
            await notify.hold_lifted(db, alert=held[0], actor=user, reason=payload.reason)
        return await run_in_threadpool(svc.overview, db, str(project_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.get("/financial-alerts")
async def list_alerts(
    project_id: UUID | None = None,
    alert_status: Literal["open", "proceed_approved", "on_hold", "resolved", "superseded"] | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Guardrail alerts, newest first."""
    return await run_in_threadpool(
        lambda: svc.list_alerts(db, project_id=str(project_id) if project_id else None, status=alert_status)
    )


@router.get("/financial-alerts/{alert_id}")
async def get_alert(
    alert_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """The decision screen: the alert, the project's health and its decision."""
    try:
        return await run_in_threadpool(svc.alert_detail, db, str(alert_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/financial-alerts/{alert_id}/decision")
async def decide_alert(
    alert_id: UUID,
    payload: AlertDecision,
    user: dict = Depends(_manager),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """OK to proceed, or hold the project, with the recorded conversation."""
    try:
        alert = await run_in_threadpool(
            lambda: svc.decide(
                db, alert_id=str(alert_id), decision=payload.decision, reason=payload.reason,
                discussed_with=str(payload.discussed_with), notes=payload.conversation_notes,
                actor_id=user["user_id"],
            )
        )
        await notify.decided(db, email_service, alert=alert, actor=user)
        return await run_in_threadpool(svc.alert_detail, db, str(alert_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc
