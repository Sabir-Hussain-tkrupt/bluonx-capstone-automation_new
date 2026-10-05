"""Task endpoints — /api/v1/projects/{project_id}/tasks"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.query_filters import escape_like_pattern
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


def _assert_unique_task_name(
    db: Client, project_id: UUID, name: str, exclude_task_id: UUID | None = None
) -> None:
    """Reject an exact duplicate task name within the same project.

    Compares the (already-trimmed) name against other non-deleted tasks in the
    project. Soft-deleted tasks don't count, so a retired name is reusable.
    """
    q = (
        db.table("tasks")
        .select("id", count="exact")
        .eq("project_id", str(project_id))
        .eq("name", name)
        .is_("deleted_at", "null")
    )
    if exclude_task_id is not None:
        q = q.neq("id", str(exclude_task_id))
    resp = q.execute()
    if resp.count and resp.count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A task named '{name}' already exists in this project.",
        )


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
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete task: it has active bid packages. "
                   "Cancel the task instead to preserve its history.",
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
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete task: it has active awards. "
                   "Cancel the task instead to preserve its history.",
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
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete task: it has active contracts. "
                   "Cancel the task instead to preserve its history.",
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

    def _filtered(select_expr: str):
        q = (
            db.table("tasks")
            .select(select_expr, count="exact")
            .eq("project_id", str(project_id))
            .is_("deleted_at", "null")
        )
        if search:
            q = q.ilike("name", f"%{escape_like_pattern(search)}%")
        if task_status:
            q = q.eq("status", task_status)
        return q

    allowed_sort = {"name", "sort_order", "status", "budget_estimate", "phase", "bid_type", "created_at"}
    if sort_by not in allowed_sort:
        sort_by = "sort_order"
    ascending = sort_dir.lower() != "desc"

    offset = (page - 1) * page_size

    # Count first, then fetch the page only when it falls within range, so a
    # page past the last row returns an empty page instead of a 416/500.
    total = _filtered("id").limit(1).execute().count or 0

    items: list = []
    if offset < total:
        resp = (
            _filtered("*, trades(name)")
            .order(sort_by, desc=not ascending)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        items = [_enrich_task(row) for row in (resp.data or [])]

    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Default Tasks Seeding Data & Endpoint ───────────────────────────────

DEFAULT_TASKS = [
    # Due Diligence Phase
    {"activity": "B0010", "name": "Land", "phase": "due_diligence", "trade": "Title", "bid_type": "internal"},
    {"activity": "B0020", "name": "Closing Costs & Commission", "phase": "due_diligence", "trade": "Title", "bid_type": "internal"},
    {"activity": "B0030", "name": "Capitalized Interest", "phase": "due_diligence", "trade": "Legal", "bid_type": "internal"},
    {"activity": "B0040", "name": "Financing Fees", "phase": "due_diligence", "trade": "Legal", "bid_type": "internal"},
    {"activity": "B0050", "name": "Real Estate Taxes", "phase": "due_diligence", "trade": "Legal", "bid_type": "internal"},
    {"activity": "B0060", "name": "Legal", "phase": "due_diligence", "trade": "Legal", "bid_type": "competitive"},
    {"activity": "B0100", "name": "Engineering and Surveying", "phase": "due_diligence", "trade": "Engineering", "bid_type": "competitive"},
    {"activity": "B0110", "name": "Zoning", "phase": "due_diligence", "trade": "Engineering", "bid_type": "internal"},
    {"activity": "B0120", "name": "Geotech - soils", "phase": "due_diligence", "trade": "Geo Tech", "bid_type": "competitive"},
    {"activity": "B0125", "name": "Geotech - Global Stability", "phase": "due_diligence", "trade": "Geo Tech", "bid_type": "competitive"},
    {"activity": "B0130", "name": "Geo Tech - Compacting Testing", "phase": "due_diligence", "trade": "Geo Tech", "bid_type": "competitive"},
    {"activity": "B0140", "name": "Environmental - Army Corps wetlands", "phase": "due_diligence", "trade": "Ecological Study", "bid_type": "competitive"},
    {"activity": "B0145", "name": "Environmental - Fisheries or Cultural", "phase": "due_diligence", "trade": "Ecological Study", "bid_type": "competitive"},
    {"activity": "B0150", "name": "Natural Resources & Mitigation", "phase": "due_diligence", "trade": "Ecological Study", "bid_type": "competitive"},

    # Development Phase
    {"activity": "B0200", "name": "Demolition", "phase": "development", "trade": "Site Final Grading", "bid_type": "competitive"},
    {"activity": "B0210", "name": "Clearing", "phase": "development", "trade": "Mass Grading", "bid_type": "competitive"},
    {"activity": "B0220", "name": "Mass Grading", "phase": "development", "trade": "Mass Grading", "bid_type": "competitive"},
    {"activity": "B0230", "name": "Grading - Clean Up", "phase": "development", "trade": "Site Final Grading", "bid_type": "competitive"},
    {"activity": "B0240", "name": "Grading Rock", "phase": "development", "trade": "Blasting", "bid_type": "competitive"},
    {"activity": "B0250", "name": "Utility Rock Excavation", "phase": "development", "trade": "Blasting", "bid_type": "competitive"},
    {"activity": "B0260", "name": "Erosion Control - silt fence and sotrm protections", "phase": "development", "trade": "Erosion Control", "bid_type": "competitive"},
    {"activity": "B0265", "name": "Street Cleaning", "phase": "development", "trade": "Erosion Control", "bid_type": "competitive"},
    {"activity": "B0270", "name": "Creek Imp./Channel Revetment", "phase": "development", "trade": "Erosion Control", "bid_type": "competitive"},
    {"activity": "B0300", "name": "Sanitary Sewers", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0310", "name": "Off-site Sanitary Sewers", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0320", "name": "Sanitary Lift Station", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0330", "name": "Sanitary Connection Prepaid Fees", "phase": "development", "trade": "Underground Utilities", "bid_type": "internal"},
    {"activity": "B0340", "name": "Storm Sewers", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0350", "name": "Off-site Storm Sewers", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0400", "name": "Water Main", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0410", "name": "Off-site Water Main", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0420", "name": "Water Main Tax", "phase": "development", "trade": "Underground Utilities", "bid_type": "internal"},
    {"activity": "B0430", "name": "Electric Install", "phase": "development", "trade": "Electric Conduit/Crossings", "bid_type": "competitive"},
    {"activity": "B0440", "name": "Street Lights", "phase": "development", "trade": "Common Ground Electric", "bid_type": "competitive"},
    {"activity": "B0450", "name": "Offsite Utilities", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0460", "name": "Utility Relocation", "phase": "development", "trade": "Underground Utilities", "bid_type": "competitive"},
    {"activity": "B0500", "name": "Concrete Streets", "phase": "development", "trade": "Paving", "bid_type": "competitive"},
    {"activity": "B0510", "name": "Asphalt Streets", "phase": "development", "trade": "Paving", "bid_type": "competitive"},
    {"activity": "B0520", "name": "Street Winter Service", "phase": "development", "trade": "Paving", "bid_type": "internal"},
    {"activity": "B0530", "name": "Common Sidewalks", "phase": "development", "trade": "Common Ground Flatwork", "bid_type": "competitive"},
    {"activity": "B0540", "name": "Asphalt Parking & Trails", "phase": "development", "trade": "Paving", "bid_type": "competitive"},
    {"activity": "B0550", "name": "TGA Fees", "phase": "development", "trade": "Engineering", "bid_type": "internal"},
    {"activity": "B0560", "name": "Offsite Roadwork", "phase": "development", "trade": "Paving", "bid_type": "competitive"},
    {"activity": "B0600", "name": "Street Signs", "phase": "development", "trade": "Street Signs", "bid_type": "competitive"},
    {"activity": "B0610", "name": "Seed & Sod", "phase": "development", "trade": "Sod", "bid_type": "competitive"},
    {"activity": "B0620", "name": "Common Landscaping", "phase": "development", "trade": "Landscaping", "bid_type": "competitive"},
    {"activity": "B0630", "name": "Irrigation", "phase": "development", "trade": "Irrigation", "bid_type": "competitive"},
    {"activity": "B0640", "name": "Entry Monuments", "phase": "development", "trade": "Monuments", "bid_type": "competitive"},
    {"activity": "B0650", "name": "Lakes/Fountains & Bubblers", "phase": "development", "trade": "Fountains and Aeration", "bid_type": "competitive"},
    {"activity": "B0660", "name": "Amenities", "phase": "development", "trade": "Common Ground Amenities", "bid_type": "competitive"},
    {"activity": "B0670", "name": "Retaining Walls", "phase": "development", "trade": "Retaining Walls", "bid_type": "competitive"},
    {"activity": "B0680", "name": "Fencing", "phase": "development", "trade": "Fencing", "bid_type": "competitive"},
    {"activity": "B0700", "name": "Permits , Inspection & Recording Fees", "phase": "development", "trade": "Engineering", "bid_type": "internal"},
    {"activity": "B0720", "name": "Contingency (not a payable category)", "phase": "development", "trade": "Engineering", "bid_type": "internal"},
    {"activity": "B0730", "name": "Developer Fee (Management Fee)", "phase": "development", "trade": "Engineering", "bid_type": "internal"},
    {"activity": "B0740", "name": "Escrow Release", "phase": "development", "trade": "Engineering", "bid_type": "internal"},
    {"activity": "B0750", "name": "HOA Overages and initiation", "phase": "development", "trade": "Engineering", "bid_type": "internal"},
    {"activity": "B0760", "name": "Post-Construction BMP and site clean up", "phase": "development", "trade": "Basins", "bid_type": "competitive"},
]

TRADE_ALIASES: dict[str, list[str]] = {
    "Geotechnical Engineering": ["Geotechnical Engineering", "Geo Tech"],
    "Geo Tech": ["Geo Tech", "Geotechnical Engineering"],
}


@router.post(
    "/projects/{project_id}/tasks/default",
    status_code=status.HTTP_201_CREATED,
    summary="Seed 58 default tasks into a project",
)
async def create_default_tasks(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Seed the standard 58 default tasks into a project."""
    project = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(project)

    # Fetch active trades
    trades_resp = db.table("trades").select("id, name").eq("is_active", True).execute()
    trades_by_name = {t["name"].strip().lower(): t["id"] for t in (trades_resp.data or [])}

    def resolve_trade_id(trade_name: str) -> str | None:
        key = trade_name.strip().lower()
        if key in trades_by_name:
            return trades_by_name[key]
        aliases = TRADE_ALIASES.get(trade_name, [])
        for alias in aliases:
            ak = alias.strip().lower()
            if ak in trades_by_name:
                return trades_by_name[ak]
        return None

    # Get existing task names for duplicate prevention
    existing_resp = (
        db.table("tasks")
        .select("name")
        .eq("project_id", str(project_id))
        .is_("deleted_at", "null")
        .execute()
    )
    existing_names = {t["name"] for t in (existing_resp.data or [])}

    # Get max sort_order
    max_resp = (
        db.table("tasks")
        .select("sort_order")
        .eq("project_id", str(project_id))
        .is_("deleted_at", "null")
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    current_sort = (max_resp.data[0]["sort_order"]) if max_resp.data else 0

    rows_to_insert = []
    skipped_count = 0

    for item in DEFAULT_TASKS:
        task_name = f"{item['activity']} - {item['name']}"
        if task_name in existing_names:
            skipped_count += 1
            continue

        trade_id = resolve_trade_id(item["trade"])
        if not trade_id:
            # Fallback to any active trade if specific trade not found
            trade_id = list(trades_by_name.values())[0] if trades_by_name else None

        if not trade_id:
            raise HTTPException(status_code=422, detail=f"Trade '{item['trade']}' could not be resolved.")

        current_sort += 1
        rows_to_insert.append({
            "project_id": str(project_id),
            "trade_id": trade_id,
            "name": task_name,
            "description": item["name"],
            "phase": item["phase"],
            "bid_type": item["bid_type"],
            "status": "draft",
            "sort_order": current_sort,
            "created_by": user["user_id"],
        })

    if rows_to_insert:
        try:
            db.table("tasks").insert(rows_to_insert).execute()
        except APIError as exc:
            logger.error("Failed to insert default tasks for project %s: %s", project_id, exc)
            raise HTTPException(status_code=422, detail="Failed to insert default tasks") from exc

    return {
        "message": f"Added {len(rows_to_insert)} default tasks. ({skipped_count} skipped as duplicates)",
        "created_count": len(rows_to_insert),
        "skipped_count": skipped_count,
    }


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


@router.get(
    "/projects/{project_id}/tasks/{task_id:uuid}",
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
    _assert_unique_task_name(db, project_id, task.name)

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
    "/projects/{project_id}/tasks/{task_id:uuid}",
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

    # Reject an exact duplicate name within the project (renames only).
    if "name" in update_data:
        _assert_unique_task_name(db, project_id, update_data["name"], exclude_task_id=task_id)

    # bid_type is locked once the task leaves draft.
    if (
        "bid_type" in update_data
        and existing["status"] != "draft"
        and update_data["bid_type"] != existing["bid_type"]
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="bid_type cannot be changed after the task leaves draft.",
        )

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
        raise HTTPException(status_code=400, detail="Task not found")

    # Re-fetch with trade join
    row = _get_task_or_404(db, project_id, task_id)
    return _enrich_task(row)


@router.delete(
    "/projects/{project_id}/tasks/{task_id:uuid}",
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
