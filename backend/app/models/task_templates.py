"""Task Template Pydantic Models"""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class TaskTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    phase: str = Field(..., pattern="^(due_diligence|development)$")
    trade_id: UUID
    bid_type: str = Field(default="competitive", pattern="^(competitive|internal|direct_assign)$")
    budget_estimate: float = Field(default=0.0, ge=0.0)
    sort_order: int = Field(default=0)
    is_active: bool = True


class TaskTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    phase: str | None = Field(default=None, pattern="^(due_diligence|development)$")
    trade_id: UUID | None = None
    bid_type: str | None = Field(default=None, pattern="^(competitive|internal|direct_assign)$")
    budget_estimate: float | None = Field(default=None, ge=0.0)
    sort_order: int | None = None
    is_active: bool | None = None


class TaskTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    phase: str
    trade_id: UUID
    trade_name: str | None = None
    bid_type: str
    budget_estimate: float = 0.0
    sort_order: int = 0
    is_active: bool = True
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TaskTemplateListResponse(BaseModel):
    items: list[TaskTemplateResponse]
    total: int
    page: int
    page_size: int
