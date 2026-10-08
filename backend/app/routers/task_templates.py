"""Task Template endpoints — /api/v1/task-templates"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.query_filters import escape_like_pattern
from app.core.supabase_client import get_supabase
from app.models.task_templates import (
    TaskTemplateCreate,
    TaskTemplateListResponse,
    TaskTemplateResponse,
    TaskTemplateUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────


def _get_template_or_404(db: Client, template_id: UUID) -> dict:
    """Fetch task template by ID, raise 404 if missing or soft-deleted."""
    try:
        resp = (
            db.table("task_templates")
            .select("*")
            .eq("id", str(template_id))
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
    except APIError as exc:
        logger.error("Failed to fetch task_templates row %s: %s", template_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch task template from database",
        ) from exc

    if not resp or not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task template not found",
        )
    return resp.data


def _validate_trade_exists(db: Client, trade_id: UUID) -> dict:
    """Check trade exists and is active."""
    try:
        resp = (
            db.table("trades")
            .select("id, name, is_active")
            .eq("id", str(trade_id))
            .maybe_single()
            .execute()
        )
    except APIError as exc:
        logger.error("Failed to fetch trade %s: %s", trade_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to validate trade",
        ) from exc

    if not resp or not resp.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trade not found",
        )
    if not resp.data.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trade is inactive",
        )
    return resp.data


def _enrich_templates(db: Client, templates: list[dict]) -> list[dict]:
    """Batch-attach trade_name to a list of task templates."""
    if not templates:
        return []

    trade_ids = list({t["trade_id"] for t in templates if t.get("trade_id")})
    trade_names: dict[str, str] = {}
    if trade_ids:
        try:
            resp = db.table("trades").select("id, name").in_("id", trade_ids).execute()
            for row in (resp.data or []):
                trade_names[str(row["id"])] = row["name"]
        except APIError as exc:
            logger.warning("Failed to batch-fetch trade names for task templates: %s", exc)

    enriched = []
    for t in templates:
        trade_id_str = str(t["trade_id"]) if t.get("trade_id") else None
        enriched.append({
            **t,
            "trade_name": trade_names.get(trade_id_str) if trade_id_str else None,
        })
    return enriched


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/task-templates", response_model=TaskTemplateListResponse)
async def list_task_templates(
    search: str | None = Query(default=None, description="Search by name"),
    phase: str | None = Query(default=None, description="Filter by phase (due_diligence, development)"),
    trade_id: UUID | None = Query(default=None, description="Filter by trade_id"),
    is_active: bool | None = Query(default=None, description="Filter by is_active status"),
    sort_by: str = Query(default="sort_order", description="Column to sort by"),
    sort_dir: str = Query(default="asc", description="Sort direction: asc or desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all task templates with search, filters, and pagination."""
    query = (
        db.table("task_templates")
        .select("*", count="exact")
        .is_("deleted_at", "null")
    )

    if search and search.strip():
        pattern = f"%{escape_like_pattern(search.strip())}%"
        query = query.or_(f"name.ilike.{pattern},description.ilike.{pattern}")

    if phase:
        query = query.eq("phase", phase)

    if trade_id:
        query = query.eq("trade_id", str(trade_id))

    if is_active is not None:
        query = query.eq("is_active", is_active)

    allowed_sort = {"name", "sort_order", "phase", "created_at", "updated_at"}
    if sort_by not in allowed_sort:
        sort_by = "sort_order"
    ascending = sort_dir.lower() != "desc"
    query = query.order(sort_by, desc=not ascending)

    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    try:
        resp = query.execute()
    except APIError as exc:
        logger.error("Failed to query task_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch task templates",
        ) from exc

    templates = resp.data or []
    enriched = _enrich_templates(db, templates)

    return TaskTemplateListResponse(
        items=enriched,
        total=resp.count or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/task-templates",
    response_model=TaskTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_template(
    payload: TaskTemplateCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new task template."""
    _validate_trade_exists(db, payload.trade_id)

    data = payload.model_dump()
    data["trade_id"] = str(payload.trade_id)
    data["created_by"] = user["user_id"]

    try:
        resp = db.table("task_templates").insert(data).execute()
    except APIError as exc:
        logger.error("Failed to insert task_template: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message or "Failed to create task template",
        ) from exc

    if not resp or not resp.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task template was created but no data was returned",
        )

    row = resp.data[0]
    enriched = _enrich_templates(db, [row])[0]
    return enriched


@router.get("/task-templates/{template_id:uuid}", response_model=TaskTemplateResponse)
async def get_task_template(
    template_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get single task template details."""
    template = _get_template_or_404(db, template_id)
    enriched = _enrich_templates(db, [template])[0]
    return enriched


@router.patch("/task-templates/{template_id:uuid}", response_model=TaskTemplateResponse)
async def update_task_template(
    template_id: UUID,
    payload: TaskTemplateUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a task template."""
    _get_template_or_404(db, template_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        template = _get_template_or_404(db, template_id)
        return _enrich_templates(db, [template])[0]

    if "trade_id" in update_data and update_data["trade_id"] is not None:
        _validate_trade_exists(db, update_data["trade_id"])
        update_data["trade_id"] = str(update_data["trade_id"])

    try:
        resp = (
            db.table("task_templates")
            .update(update_data)
            .eq("id", str(template_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Failed to update task_template %s: %s", template_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message or "Failed to update task template",
        ) from exc

    if not resp or not resp.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task template was updated but no data was returned",
        )

    row = resp.data[0]
    return _enrich_templates(db, [row])[0]


@router.delete("/task-templates/{template_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_template(
    template_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft delete a task template."""
    _get_template_or_404(db, template_id)

    try:
        db.table("task_templates").update({
            "deleted_at": "now()",
            "is_active": False,
        }).eq("id", str(template_id)).execute()
    except APIError as exc:
        logger.error("Failed to soft-delete task_template %s: %s", template_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to delete task template",
        ) from exc
