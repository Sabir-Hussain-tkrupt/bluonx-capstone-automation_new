"""Project endpoints — /api/v1/projects"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.projects import (
    ProjectCreate,
    ProjectDocumentCreate,
    ProjectDocumentResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter()


# ── Projects CRUD ────────────────────────────────────────────────────────


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all active projects."""
    # TODO: Implement in Phase 3
    return []


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single project by ID."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new project."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project: ProjectUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a project."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a project (sets deleted_at)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Project Documents ────────────────────────────────────────────────────


@router.get("/projects/{project_id}/documents", response_model=list[ProjectDocumentResponse])
async def list_project_documents(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List documents for a project."""
    # TODO: Implement in Phase 3
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
    # TODO: Implement in Phase 3
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
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")
