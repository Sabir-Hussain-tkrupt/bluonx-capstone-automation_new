"""
Pydantic models for communication and audit tables:
  - email_log
  - vendor_flags
  - notifications
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.models.common import BluOnXBase


# ── email_log ────────────────────────────────────────────────────────────

EMAIL_TYPES = Literal[
    "bid_invitation", "bid_reminder", "award_notification",
    "decline_notification", "milestone_alert", "general",
]

EMAIL_STATUSES = Literal[
    "queued", "sent", "delivered", "bounced", "failed",
]


class EmailLogCreate(BluOnXBase):
    recipient_email: str
    recipient_type: Literal["vendor_contact", "user"]
    email_type: EMAIL_TYPES
    subject: str | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None


class EmailLogUpdate(BluOnXBase):
    status: EMAIL_STATUSES | None = None
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    clicked_at: datetime | None = None
    error_message: str | None = None


class EmailLogResponse(BluOnXBase):
    id: UUID
    recipient_email: str
    recipient_type: str
    email_type: str
    subject: str | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None
    status: str
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    clicked_at: datetime | None = None
    error_message: str | None = None
    retry_count: int
    created_at: datetime


# ── vendor_flags ─────────────────────────────────────────────────────────

FLAG_REASONS = Literal[
    "missed_deadline", "poor_quality", "unresponsive", "other",
]


class VendorFlagCreate(BluOnXBase):
    vendor_id: UUID
    reason: FLAG_REASONS
    notes: str | None = None
    milestone_id: UUID | None = None


class VendorFlagUpdate(BluOnXBase):
    is_resolved: bool | None = None
    notes: str | None = None


class VendorFlagResponse(BluOnXBase):
    id: UUID
    vendor_id: UUID
    flagged_by: UUID
    reason: str
    notes: str | None = None
    milestone_id: UUID | None = None
    is_resolved: bool
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None
    created_at: datetime


# ── notifications ────────────────────────────────────────────────────────


class NotificationCreate(BluOnXBase):
    user_id: UUID
    title: str
    message: str | None = None
    notification_type: str
    reference_type: str | None = None
    reference_id: UUID | None = None


class NotificationUpdate(BluOnXBase):
    is_read: bool | None = None


class NotificationResponse(BluOnXBase):
    id: UUID
    user_id: UUID
    title: str
    message: str | None = None
    notification_type: str
    reference_type: str | None = None
    reference_id: UUID | None = None
    is_read: bool
    created_at: datetime
