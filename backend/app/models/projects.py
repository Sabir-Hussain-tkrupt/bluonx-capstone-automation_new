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

from pydantic import Field, field_validator, model_validator

from app.models.common import BluOnXBase


# ── shared field/cross-field validators ──────────────────────────────────


def _require_nonblank_name(v: str | None) -> str | None:
    """Trim surrounding whitespace and reject blank/whitespace-only names.

    Runs after the min_length/max_length constraints, so a value like "  "
    passes the raw length check but is caught here once stripped. The trimmed
    value is what gets stored.
    """
    if v is None:
        return v
    v = v.strip()
    if len(v) < 2:
        raise ValueError("name must contain at least 2 non-whitespace characters")
    return v


def _require_end_after_start(start: date | None, end: date | None) -> None:
    """Raise if estimated_end_date precedes start_date (both must be set)."""
    if start and end and end < start:
        raise ValueError("estimated_end_date must be on or after start_date")


# ── projects ─────────────────────────────────────────────────────────────


class ProjectCreate(BluOnXBase):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
    budget: Decimal | None = Field(default=None, ge=0)
    status: Literal["planning", "active", "on_hold", "completed", "cancelled"] = "planning"
    start_date: date | None = None
    estimated_end_date: date | None = None

    _strip_name = field_validator("name")(_require_nonblank_name)

    @model_validator(mode="after")
    def _validate_dates(self):
        _require_end_after_start(self.start_date, self.estimated_end_date)
        return self


class ProjectUpdate(BluOnXBase):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
    budget: Decimal | None = Field(default=None, ge=0)
    status: Literal["planning", "active", "on_hold", "completed", "cancelled"] | None = None
    start_date: date | None = None
    estimated_end_date: date | None = None

    _strip_name = field_validator("name")(_require_nonblank_name)

    @model_validator(mode="after")
    def _validate_dates(self):
        # Catches the case where both dates are supplied in one PATCH. The
        # partial case (only one supplied, the other already stored) is checked
        # in the router against the existing row.
        _require_end_after_start(self.start_date, self.estimated_end_date)
        return self


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
    #: Set only on create/update when geocoding could not refresh this row's
    #: coordinates. Null on reads. Non-fatal: the write succeeded, but the
    #: record will not take part in distance filtering until the address is
    #: fixed. Surfaced to the user as a warning toast.
    geocode_warning: str | None = None
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

    _strip_name = field_validator("name")(_require_nonblank_name)


class TaskUpdate(BluOnXBase):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    trade_id: UUID | None = None
    phase: Literal["due_diligence", "development"] | None = None
    bid_type: Literal["competitive", "direct_assign", "internal"] | None = None
    budget_estimate: Decimal | None = Field(default=None, ge=0)
    sort_order: int | None = Field(default=None, ge=0)
    status: TASK_STATUSES | None = None

    _strip_name = field_validator("name")(_require_nonblank_name)


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
    sort_order: int = Field(..., ge=0)
