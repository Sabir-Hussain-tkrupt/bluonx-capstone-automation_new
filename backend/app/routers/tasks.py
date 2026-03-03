"""Task endpoints — /api/v1/tasks"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.projects import TaskCreate, TaskResponse, TaskUpdate

router = APIRouter()


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    project_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List tasks, optionally filtered by project_id."""
    # TODO: Implement in Phase 3
    return []


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single task by ID."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new task."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    task: TaskUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a task."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a task (sets deleted_at)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")
