"""Project budget endpoints — /api/v1/projects/{id}/budget, /budget-lines, /land-closings

Writes only (plus export). Reads stay on the frontend's direct Supabase path:
v_budget_lines and v_project_budget_summary under RLS, any active user.

Every write is `Depends(require_admin)` — only admins create and edit budgets,
matching today's admin-only project budget rule — and that check is the real
gate: these handlers hold the service_role key, which bypasses RLS.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from supabase import Client

from app.core.auth import get_current_active_user, require_admin
from app.core.supabase_client import get_supabase
from app.models.budgets import (
    BudgetCreate,
    BudgetLineCreate,
    BudgetLineUpdate,
    LandClosingCreate,
    LandClosingUpdate,
    ReorderRequest,
    SyncAwardsResult,
)
from app.services import budget_award_sync, budget_import_export, budget_service
from app.services.financial_errors import FinancialError

router = APIRouter()


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# ── Budget lifecycle ────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/budget", status_code=status.HTTP_201_CREATED)
async def create_budget(
    project_id: UUID,
    payload: BudgetCreate | None = None,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Create the project's draft budget from the standard template; every task
    becomes a line (admin only)."""
    payload = payload or BudgetCreate()
    try:
        lines = await run_in_threadpool(
            budget_service.create_budget,
            db,
            project_id=str(project_id),
            actor_id=user["user_id"],
            template_id=str(payload.template_id) if payload.template_id else None,
            contingency_percent=payload.contingency_percent,
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    return {"line_count": len(lines)}


@router.post("/projects/{project_id}/budget/baseline")
async def baseline_budget(
    project_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Freeze the estimates and make the total flat (admin only)."""
    try:
        project = await run_in_threadpool(
            budget_service.baseline_budget, db, project_id=str(project_id), actor_id=user["user_id"]
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    return {
        "budget_status": project.get("budget_status"),
        "approved_budget_total": project.get("approved_budget_total"),
    }


@router.post("/projects/{project_id}/budget/sync-awards", response_model=SyncAwardsResult)
async def sync_awards(
    project_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Re-apply active awards and lock executed contracts on every bid line.
    Idempotent safety net for the award / DocuSign hooks (admin only)."""
    try:
        budget_service.get_project(db, str(project_id))
    except FinancialError as exc:
        raise _http(exc) from exc
    return await run_in_threadpool(budget_award_sync.sync_project, db, str(project_id), user["user_id"])


# ── Lines ───────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/budget/lines", status_code=status.HTTP_201_CREATED)
async def add_line(
    project_id: UUID,
    payload: BudgetLineCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Add a line without a task: land, permit, impact fee, soft cost, long-tail,
    or an internal T&M portion (admin only)."""
    try:
        return await run_in_threadpool(
            budget_service.add_line, db, project_id=str(project_id), payload=payload, actor_id=user["user_id"]
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.put("/projects/{project_id}/budget/lines/order")
async def reorder_lines(
    project_id: UUID,
    payload: ReorderRequest,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Reorder every live line of the budget (admin only)."""
    try:
        lines = await run_in_threadpool(
            budget_service.reorder_lines, db, project_id=str(project_id),
            line_ids=payload.line_ids, actor_id=user["user_id"],
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    return {"line_count": len(lines)}


@router.patch("/budget-lines/{line_id}")
async def update_line(
    line_id: UUID,
    payload: BudgetLineUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Edit amount (draft), dates, payment terms, cash bucket, heading (admin only)."""
    try:
        return await run_in_threadpool(
            budget_service.update_line, db, line_id=str(line_id), payload=payload, actor_id=user["user_id"]
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.delete("/budget-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_line(
    line_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Remove a line that is not needed (admin only). Task lines go with their task."""
    try:
        await run_in_threadpool(budget_service.remove_line, db, line_id=str(line_id), actor_id=user["user_id"])
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Land closings ───────────────────────────────────────────────────────────


@router.post("/budget-lines/{line_id}/closings", status_code=status.HTTP_201_CREATED)
async def add_closing(
    line_id: UUID,
    payload: LandClosingCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Add a phased land closing (admin only)."""
    try:
        return await run_in_threadpool(
            budget_service.add_closing, db, line_id=str(line_id), payload=payload, actor_id=user["user_id"]
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.patch("/land-closings/{closing_id}")
async def update_closing(
    closing_id: UUID,
    payload: LandClosingUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Edit, close or cancel a phased land closing (admin only)."""
    try:
        return await run_in_threadpool(
            budget_service.update_closing, db, closing_id=str(closing_id), payload=payload
        )
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Import / export (Task 2.8) ──────────────────────────────────────────────


@router.get("/projects/{project_id}/budget/export")
async def export_budget(
    project_id: UUID,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Download the budget as Excel or CSV (any active user)."""
    try:
        filename, content_type, body = await run_in_threadpool(
            budget_import_export.export_budget, db, str(project_id), format
        )
    except FinancialError as exc:
        raise _http(exc) from exc
    return Response(
        content=body,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/projects/{project_id}/budget/import/preview")
async def import_preview(
    project_id: UUID,
    file: UploadFile = File(...),
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Parse a CSV / Excel budget and match it to the draft budget (admin only).
    Nothing is written."""
    content = await file.read()
    try:
        return await run_in_threadpool(
            budget_import_export.preview_import, db, str(project_id), file.filename or "", content
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/projects/{project_id}/budget/import/apply")
async def import_apply(
    project_id: UUID,
    payload: budget_import_export.ImportApplyRequest,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Apply confirmed import rows to the draft budget in one transaction (admin only)."""
    try:
        return await run_in_threadpool(
            budget_import_export.apply_import, db, str(project_id), payload.rows, user["user_id"]
        )
    except FinancialError as exc:
        raise _http(exc) from exc
