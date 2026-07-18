"""Task endpoints — /api/v1/projects/{project_id}/tasks"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.projects import (
    TaskCreate,
    TaskListResponse,
    TaskReorderItem,
    TaskResponse,
    TaskUpdate,
)
from app.models.vendor_filtering import QualifiedVendorsResponse
from app.services.vendor_filtering import filter_qualified_vendors

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Status transition map ────────────────────────────────────────────────

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"bidding", "cancelled"},
    "bidding": {"evaluating", "cancelled"},
    "evaluating": {"awarded", "cancelled"},
    "awarded": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": {"draft"},
}


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_project_or_404(db: Client, project_id: UUID) -> dict:
    """Verify project exists and is not soft-deleted."""
    resp = (
        db.table("projects")
        .select("id, name, budget, archived_at")
        .eq("id", str(project_id))
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return resp.data


def _ensure_project_not_archived(project: dict) -> None:
    """Block mutations on a project once it is archived."""
    if project.get("archived_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify tasks on an archived project. Unarchive it first.",
        )


def _get_task_or_404(db: Client, project_id: UUID, task_id: UUID) -> dict:
    """Fetch a task, ensure it belongs to the project and is not deleted."""
    resp = (
        db.table("tasks")
        .select("*, trades(name)")
        .eq("id", str(task_id))
        .eq("project_id", str(project_id))
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise HTTPException(status_code=404, detail="Task not found")
    return resp.data


def _validate_trade_for_phase(db: Client, trade_id: UUID, phase: str) -> dict:
    """Check trade exists, is active, and phase-compatible."""
    resp = (
        db.table("trades")
        .select("id, name, phase, is_active")
        .eq("id", str(trade_id))
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise HTTPException(status_code=422, detail="Trade not found")

    trade = resp.data
    if not trade["is_active"]:
        raise HTTPException(status_code=422, detail="Trade is inactive")

    if trade["phase"] != "both" and trade["phase"] != phase:
        raise HTTPException(
            status_code=422,
            detail=f"Trade '{trade['name']}' (phase={trade['phase']}) is not valid for task phase '{phase}'",
        )
    return trade


def _check_deletion_blockers(db: Client, task_id: UUID) -> None:
    """Block deletion if active bid_packages, awards, or contracts exist."""
    tid = str(task_id)

    # Active bid packages
    bp = (
        db.table("bid_packages")
        .select("id", count="exact")
        .eq("task_id", tid)
        .not_.in_("status", ["completed", "cancelled"])
        .execute()
    )
    if bp.count and bp.count > 0:
        raise HTTPException(
            status_code=422,
            detail="Cannot delete task: active bid packages exist",
        )

    # Active awards
    aw = (
        db.table("awards")
        .select("id", count="exact")
        .eq("task_id", tid)
        .not_.in_("status", ["declined", "revoked"])
        .execute()
    )
    if aw.count and aw.count > 0:
        raise HTTPException(
            status_code=422,
            detail="Cannot delete task: active awards exist",
        )

    # Active contracts
    ct = (
        db.table("contracts")
        .select("id", count="exact")
        .eq("task_id", tid)
        .not_.in_("status", ["terminated", "completed"])
        .execute()
    )
    if ct.count and ct.count > 0:
        raise HTTPException(
            status_code=422,
            detail="Cannot delete task: active contracts exist",
        )


def _enrich_task(row: dict) -> dict:
    """Flatten the joined trades data into trade_name."""
    trades_data = row.pop("trades", None)
    row["trade_name"] = trades_data["name"] if trades_data else None
    return row


# ── CRUD Endpoints ───────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/tasks",
    response_model=TaskListResponse,
)
async def list_tasks(
    project_id: UUID,
    search: str | None = Query(default=None, description="Search by task name"),
    task_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    sort_by: str = Query(default="sort_order", description="Column to sort by"),
    sort_dir: str = Query(default="asc", description="Sort direction: asc or desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List tasks for a project, sorted by sort_order."""
    _get_project_or_404(db, project_id)

    query = (
        db.table("tasks")
        .select("*, trades(name)", count="exact")
        .eq("project_id", str(project_id))
        .is_("deleted_at", "null")
    )

    if search:
        query = query.ilike("name", f"%{search}%")

    if task_status:
        query = query.eq("status", task_status)

    allowed_sort = {"name", "sort_order", "status", "budget_estimate", "phase", "bid_type", "created_at"}
    if sort_by not in allowed_sort:
        sort_by = "sort_order"

    ascending = sort_dir.lower() != "desc"
    query = query.order(sort_by, desc=not ascending)

    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    resp = query.execute()

    items = [_enrich_task(row) for row in (resp.data or [])]

    return TaskListResponse(
        items=items,
        total=resp.count or 0,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/projects/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
)
async def get_task(
    project_id: UUID,
    task_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single task by ID."""
    _get_project_or_404(db, project_id)
    row = _get_task_or_404(db, project_id, task_id)
    return _enrich_task(row)


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    project_id: UUID,
    task: TaskCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new task within a project."""
    project = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(project)
    trade = _validate_trade_for_phase(db, task.trade_id, task.phase)

    # Calculate next sort_order
    max_resp = (
        db.table("tasks")
        .select("sort_order")
        .eq("project_id", str(project_id))
        .is_("deleted_at", "null")
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    next_sort = (max_resp.data[0]["sort_order"] + 1) if max_resp.data else 1

    task_data = task.model_dump()
    task_data["project_id"] = str(project_id)
    task_data["trade_id"] = str(task.trade_id)
    task_data["created_by"] = user["user_id"]
    task_data["sort_order"] = next_sort
    task_data["status"] = "draft"

    # Convert Decimal to string
    if task_data.get("budget_estimate") is not None:
        task_data["budget_estimate"] = str(task_data["budget_estimate"])

    try:
        resp = db.table("tasks").insert(task_data).execute()
    except APIError as exc:
        logger.error("Supabase insert failed for tasks: %s", exc)
        raise HTTPException(
            status_code=422,
            detail="The submitted data was rejected. Please review the values and try again.",
        ) from exc

    if not resp.data:
        raise HTTPException(status_code=400, detail="Failed to create task")

    created = resp.data[0]
    created["trade_name"] = trade["name"]
    return created


@router.patch(
    "/projects/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
)
async def update_task(
    project_id: UUID,
    task_id: UUID,
    task: TaskUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a task."""
    project = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(project)
    existing = _get_task_or_404(db, project_id, task_id)
    # Remove trades join data for comparison
    existing.pop("trades", None)

    update_data = task.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate status transition
    if "status" in update_data:
        current_status = existing["status"]
        new_status = update_data["status"]
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot transition from '{current_status}' to '{new_status}'. "
                       f"Allowed: {sorted(allowed) if allowed else 'none'}",
            )

    # If phase or trade_id changed, re-validate trade-phase compatibility
    new_phase = update_data.get("phase", existing["phase"])
    new_trade_id = update_data.get("trade_id", existing["trade_id"])
    if "phase" in update_data or "trade_id" in update_data:
        _validate_trade_for_phase(db, UUID(str(new_trade_id)), new_phase)

    # Convert types for Supabase
    if "trade_id" in update_data and update_data["trade_id"] is not None:
        update_data["trade_id"] = str(update_data["trade_id"])
    if "budget_estimate" in update_data and update_data["budget_estimate"] is not None:
        update_data["budget_estimate"] = str(update_data["budget_estimate"])

    try:
        resp = (
            db.table("tasks")
            .update(update_data)
            .eq("id", str(task_id))
            .eq("project_id", str(project_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase update failed for tasks/%s: %s", task_id, exc)
        raise HTTPException(
            status_code=422,
            detail="The submitted data was rejected. Please review the values and try again.",
        ) from exc

    if not resp.data:
        raise HTTPException(status_code=404, detail="Task not found")

    # Re-fetch with trade join
    row = _get_task_or_404(db, project_id, task_id)
    return _enrich_task(row)


@router.delete(
    "/projects/{project_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task(
    project_id: UUID,
    task_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a task. Blocked if active bids/awards/contracts exist."""
    project = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(project)
    _get_task_or_404(db, project_id, task_id)
    _check_deletion_blockers(db, task_id)

    resp = (
        db.table("tasks")
        .update({"deleted_at": "now()"})
        .eq("id", str(task_id))
        .eq("project_id", str(project_id))
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=404, detail="Task not found")


@router.put(
    "/projects/{project_id}/tasks/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reorder_tasks(
    project_id: UUID,
    items: list[TaskReorderItem],
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Bulk update sort_order for tasks within a project."""
    project = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(project)

    for item in items:
        db.table("tasks").update(
            {"sort_order": item.sort_order}
        ).eq("id", str(item.task_id)).eq(
            "project_id", str(project_id)
        ).is_("deleted_at", "null").execute()


# ── Vendor Filtering ────────────────────────────────────────────────────


@router.get(
    "/tasks/{task_id}/qualified-vendors",
    response_model=QualifiedVendorsResponse,
)
async def get_qualified_vendors(
    task_id: UUID,
    radius_miles: float = Query(default=75, ge=1, le=500, description="Max distance in miles"),
    include_flagged: bool = Query(default=True, description="Include vendors with unresolved flags"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Find qualified vendors for a competitive task.

    Runs the multi-stage filtering pipeline: trade match, status,
    onboarding, insurance, bonding, capacity, distance, and flags.
    Returns qualified and disqualified vendors with detailed reasons.
    """
    try:
        return await filter_qualified_vendors(
            db=db,
            task_id=str(task_id),
            radius_miles=radius_miles,
            include_flagged=include_flagged,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
    except Exception as exc:
        logger.error(
            "Vendor filtering failed for task %s: [%s] %s",
            task_id, type(exc).__name__, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to filter vendors",
        ) from exc
