"""Project notes endpoints — /api/v1/projects/{id}/notes, /api/v1/project-notes/{id}"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.project_notes import ProjectNoteCreate, ProjectNoteResponse, ProjectNoteUpdate
from app.services import project_note_service as svc

router = APIRouter()


@router.get("/projects/{project_id}/notes", response_model=list[ProjectNoteResponse])
async def list_project_notes(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Notes on a project, most recently updated first."""
    return svc.list_notes(db, user, project_id)


@router.post(
    "/projects/{project_id}/notes",
    response_model=ProjectNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_note(
    project_id: UUID,
    body: ProjectNoteCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Add a note (any active user)."""
    return svc.create_note(db, user, project_id, body)


@router.patch("/project-notes/{note_id}", response_model=ProjectNoteResponse)
async def update_project_note(
    note_id: UUID,
    body: ProjectNoteUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Edit a note (author or admin)."""
    return svc.update_note(db, user, note_id, body)


@router.delete("/project-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_note(
    note_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a note (author or admin). Soft delete."""
    svc.delete_note(db, user, note_id)
