"""
Pydantic models for milestone tracking tables:
  - milestones
  - milestone_responses
  - milestone_alerts
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


# ── milestones ───────────────────────────────────────────────────────────

# Migrated 6-status set (see database/bluonx_complete_schema.sql milestones CHECK).
MILESTONE_STATUSES = Literal[
    "scheduled", "in_progress", "delayed", "unresponsive", "completed", "cancelled",
]


class MilestoneCreate(BluOnXBase):
    task_id: UUID  # contract_id is resolved server-side from the task's active contract
    name: str = Field(min_length=1, max_length=255)
    start_date: date
    end_date: date
    notes: str | None = None


class MilestoneUpdate(BluOnXBase):
    # status is NOT settable here — status changes only via the action endpoints.
    name: str | None = Field(default=None, min_length=1, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None
    sort_order: int | None = None


# ── milestone action bodies ──────────────────────────────────────────────


class MilestoneMarkStarted(BluOnXBase):
    actual_start_date: date | None = None


class MilestoneMarkCompleted(BluOnXBase):
    actual_end_date: date | None = None


class MilestoneReschedule(BluOnXBase):
    end_date: date


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
