"""Standard budget template endpoints — /api/v1/budget-templates (admin only).

Writes only. The Settings → Budget Template page reads budget_templates /
budget_template_lines directly from Supabase (RLS: any active user).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.core.auth import require_admin
from app.core.supabase_client import get_supabase
from app.models.budgets import ReorderRequest, TemplateLineCreate, TemplateLineUpdate
from app.services import budget_template_service
from app.services.financial_errors import FinancialError

router = APIRouter()


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/budget-templates/{template_id}/lines", status_code=status.HTTP_201_CREATED)
async def add_template_line(
    template_id: UUID,
    payload: TemplateLineCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    try:
        return await run_in_threadpool(
            budget_template_service.add_line, db, template_id=str(template_id), payload=payload
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.patch("/budget-template-lines/{line_id}")
async def update_template_line(
    line_id: UUID,
    payload: TemplateLineUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    try:
        return await run_in_threadpool(
            budget_template_service.update_line, db, line_id=str(line_id), payload=payload
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.delete("/budget-template-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template_line(
    line_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    try:
        await run_in_threadpool(budget_template_service.delete_line, db, line_id=str(line_id))
    except FinancialError as exc:
        raise _http(exc) from exc


@router.put("/budget-templates/{template_id}/lines/order")
async def reorder_template_lines(
    template_id: UUID,
    payload: ReorderRequest,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    try:
        lines = await run_in_threadpool(
            budget_template_service.reorder_lines, db, template_id=str(template_id), line_ids=payload.line_ids
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    return {"line_count": len(lines)}
