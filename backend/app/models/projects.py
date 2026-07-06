"""
Pydantic models for project-related tables:
  - projects
  - project_documents
  - tasks
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


# ── projects ─────────────────────────────────────────────────────────────


class ProjectCreate(BluOnXBase):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    status: Literal["planning", "active", "on_hold", "completed", "cancelled"] = "planning"
    start_date: date | None = None
    estimated_end_date: date | None = None


class ProjectUpdate(BluOnXBase):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    status: Literal["planning", "active", "on_hold", "completed", "cancelled"] | None = None
    start_date: date | None = None
    estimated_end_date: date | None = None


class ProjectResponse(BluOnXBase):
    id: UUID
    name: str
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    budget: Decimal | None = None
    status: str
    start_date: date | None = None
    estimated_end_date: date | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    archived_at: datetime | None = None
    archived_by: UUID | None = None


class ProjectListResponse(BluOnXBase):
    """Paginated project list response."""
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int


# ── project_documents ────────────────────────────────────────────────────


class ProjectDocumentCreate(BluOnXBase):
    project_id: UUID
    file_name: str
    file_path: str
    file_type: str | None = None
    file_size: int | None = None


class ProjectDocumentResponse(BluOnXBase):
    id: UUID
    project_id: UUID
    file_name: str
    file_path: str
    file_type: str | None = None
    file_size: int | None = None
    document_kind: str = "reference"
    uploaded_by: UUID
    uploaded_at: datetime


# ── tasks ────────────────────────────────────────────────────────────────

TASK_STATUSES = Literal[
    "draft", "bidding", "evaluating", "awarded",
    "in_progress", "completed", "cancelled",
]


class TaskCreate(BluOnXBase):
    trade_id: UUID
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    phase: Literal["due_diligence", "development"]
    bid_type: Literal["competitive", "direct_assign", "internal"]
    budget_estimate: Decimal | None = Field(default=None, ge=0)


class TaskUpdate(BluOnXBase):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    trade_id: UUID | None = None
    phase: Literal["due_diligence", "development"] | None = None
    bid_type: Literal["competitive", "direct_assign", "internal"] | None = None
    budget_estimate: Decimal | None = Field(default=None, ge=0)
    sort_order: int | None = None
    status: TASK_STATUSES | None = None


class TaskResponse(BluOnXBase):
    id: UUID
    project_id: UUID
    trade_id: UUID
    name: str
    description: str | None = None
    phase: str
    bid_type: str
    budget_estimate: Decimal | None = None
    sort_order: int
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    trade_name: str | None = None


class TaskListResponse(BluOnXBase):
    items: list[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskReorderItem(BluOnXBase):
    task_id: UUID
    sort_order: int
