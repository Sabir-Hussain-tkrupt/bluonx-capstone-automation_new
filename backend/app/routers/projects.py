"""Project endpoints — /api/v1/projects"""

from uuid import UUID

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.projects import (
    ProjectCreate,
    ProjectDocumentCreate,
    ProjectDocumentResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter()


# ── Helper: verify project exists and is not soft-deleted ────────────────


def _get_project_or_404(db: Client, project_id: UUID) -> dict:
    """Fetch a project by ID, raise 404 if not found or soft-deleted."""
    response = (
        db.table("projects")
        .select("*")
        .eq("id", str(project_id))
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return response.data


# ── Projects CRUD ────────────────────────────────────────────────────────


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    search: str | None = Query(default=None, description="Search by project name"),
    project_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    sort_by: str = Query(default="name", description="Column to sort by"),
    sort_dir: str = Query(default="asc", description="Sort direction: asc or desc"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all active projects with search, filter, sort, and pagination."""

    query = db.table("projects").select("*", count="exact").is_("deleted_at", "null")

    if search:
        query = query.ilike("name", f"%{search}%")

    if project_status:
        query = query.eq("status", project_status)

    # Sorting
    allowed_sort_columns = {
        "name", "city", "status", "budget", "start_date", "created_at",
    }
    if sort_by not in allowed_sort_columns:
        sort_by = "name"

    ascending = sort_dir.lower() != "desc"
    query = query.order(sort_by, desc=not ascending)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    response = query.execute()

    return ProjectListResponse(
        items=response.data or [],
        total=response.count or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single project by ID."""
    return _get_project_or_404(db, project_id)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new project. created_by is set from the authenticated user."""
    project_data = project.model_dump()
    project_data["created_by"] = user["user_id"]

    # Convert Decimal fields to string for JSON serialization
    for key in ("budget", "latitude", "longitude"):
        if project_data.get(key) is not None:
            project_data[key] = str(project_data[key])

    # Convert date fields to string
    for key in ("start_date", "estimated_end_date"):
        if project_data.get(key) is not None:
            project_data[key] = project_data[key].isoformat()

    try:
        response = db.table("projects").insert(project_data).execute()
    except APIError as exc:
        logger.error("Supabase insert failed for projects: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create project",
        )

    return response.data[0]


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project: ProjectUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a project."""
    _get_project_or_404(db, project_id)

    update_data = project.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Convert Decimal fields to string for JSON serialization
    for key in ("budget", "latitude", "longitude"):
        if key in update_data and update_data[key] is not None:
            update_data[key] = str(update_data[key])

    # Convert date fields to string
    for key in ("start_date", "estimated_end_date"):
        if key in update_data and update_data[key] is not None:
            update_data[key] = update_data[key].isoformat()

    try:
        response = (
            db.table("projects")
            .update(update_data)
            .eq("id", str(project_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase update failed for projects/%s: %s", project_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return response.data[0]


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a project (sets deleted_at)."""
    _get_project_or_404(db, project_id)

    response = (
        db.table("projects")
        .update({"deleted_at": "now()"})
        .eq("id", str(project_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )


# ── Project Documents ────────────────────────────────────────────────────


@router.get("/projects/{project_id}/documents", response_model=list[ProjectDocumentResponse])
async def list_project_documents(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List documents for a project."""
    # TODO: Implement in Task 3.4
    return []


@router.post(
    "/projects/{project_id}/documents",
    response_model=ProjectDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_document(
    project_id: UUID,
    document: ProjectDocumentCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Upload a document for a project."""
    # TODO: Implement in Task 3.4
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete(
    "/projects/{project_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_document(
    project_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a project document."""
    # TODO: Implement in Task 3.4
    raise HTTPException(status_code=501, detail="Not implemented")
