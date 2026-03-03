"""
Pydantic models for milestone tracking tables:
  - milestones
  - milestone_responses
  - milestone_alerts
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.models.common import BluOnXBase


# ── milestones ───────────────────────────────────────────────────────────

MILESTONE_STATUSES = Literal[
    "scheduled", "started", "on_track", "delayed", "completed",
]


class MilestoneCreate(BluOnXBase):
    task_id: UUID  # denormalized, validated by DB trigger
    contract_id: UUID
    name: str
    start_date: date
    end_date: date
    sort_order: int = 0
    notes: str | None = None


class MilestoneUpdate(BluOnXBase):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    status: MILESTONE_STATUSES | None = None
    sort_order: int | None = None
    notes: str | None = None


class MilestoneResponse(BluOnXBase):
    id: UUID
    task_id: UUID
    contract_id: UUID
    name: str
    start_date: date
    end_date: date
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    status: str
    sort_order: int
    notes: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


# ── milestone_responses ──────────────────────────────────────────────────

MILESTONE_RESPONSE_TYPES = Literal[
    "start_confirmation", "progress_check", "completion_confirmation",
]


class MilestoneResponseCreate(BluOnXBase):
    milestone_id: UUID
    response_type: MILESTONE_RESPONSE_TYPES
    response_value: Literal["yes", "no"]
    response_token_hash: str
    vendor_contact_id: UUID


class MilestoneResponseSchema(BluOnXBase):
    """Named *Schema to avoid collision with MilestoneResponse above."""

    id: UUID
    milestone_id: UUID
    response_type: str
    response_value: str
    response_token_hash: str
    vendor_contact_id: UUID
    responded_at: datetime


# ── milestone_alerts ─────────────────────────────────────────────────────

MILESTONE_ALERT_TYPES = Literal[
    "starting_soon", "start_check", "progress_check", "completion_check",
    "delay_alert", "no_response_alert", "completion_notification",
]


class MilestoneAlertCreate(BluOnXBase):
    milestone_id: UUID
    email_log_id: UUID | None = None
    alert_type: MILESTONE_ALERT_TYPES
    recipient_type: Literal["vendor", "pm"]
    response_token_hash: str | None = None


class MilestoneAlertResponse(BluOnXBase):
    id: UUID
    milestone_id: UUID
    email_log_id: UUID | None = None
    alert_type: str
    recipient_type: str
    response_token_hash: str | None = None
    created_at: datetime
