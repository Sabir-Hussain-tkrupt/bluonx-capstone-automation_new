"""
Pydantic models for award and contract tables:
  - awards
  - contracts
  - docusign_envelopes
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


# ── awards ───────────────────────────────────────────────────────────────

AWARD_STATUSES = Literal[
    "pending_acceptance", "accepted", "declined_by_vendor", "cancelled",
]


class AwardCreate(BluOnXBase):
    task_id: UUID  # denormalized, validated by DB trigger
    bid_submission_id: UUID
    vendor_id: UUID  # denormalized, validated by DB trigger
    award_amount: Decimal = Field(ge=0)
    has_override: bool = False
    override_justification: str | None = None
    validation_results: dict | None = None


class AwardUpdate(BluOnXBase):
    status: AWARD_STATUSES | None = None
    override_justification: str | None = None


class AwardResponse(BluOnXBase):
    id: UUID
    task_id: UUID
    bid_submission_id: UUID
    vendor_id: UUID
    awarded_by: UUID
    awarded_at: datetime
    award_amount: Decimal
    has_override: bool
    override_justification: str | None = None
    validation_results: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime


# ── contracts ────────────────────────────────────────────────────────────

CONTRACT_STATUSES = Literal[
    "draft", "sent_for_signature", "executed", "active", "completed", "terminated",
]


class ContractCreate(BluOnXBase):
    award_id: UUID
    vendor_id: UUID  # denormalized, validated by DB trigger
    task_id: UUID  # denormalized, validated by DB trigger
    contract_number: str
    start_date: date | None = None
    end_date: date | None = None
    contract_amount: Decimal = Field(ge=0)
    payment_terms: str | None = None
    status: CONTRACT_STATUSES = "draft"


class ContractUpdate(BluOnXBase):
    start_date: date | None = None
    end_date: date | None = None
    payment_terms: str | None = None
    status: CONTRACT_STATUSES | None = None


class ContractResponse(BluOnXBase):
    id: UUID
    award_id: UUID
    vendor_id: UUID
    task_id: UUID
    contract_number: str
    start_date: date | None = None
    end_date: date | None = None
    contract_amount: Decimal
    payment_terms: str | None = None
    status: str
    signed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── docusign_envelopes ───────────────────────────────────────────────────

DOCUSIGN_STATUSES = Literal[
    "sent", "delivered", "signed", "completed", "declined", "voided",
]


class DocuSignEnvelopeCreate(BluOnXBase):
    contract_id: UUID
    envelope_id: str
    sent_at: datetime | None = None


class DocuSignEnvelopeUpdate(BluOnXBase):
    status: DOCUSIGN_STATUSES | None = None
    completed_at: datetime | None = None
    document_url: str | None = None
    webhook_payload: dict | None = None


class DocuSignEnvelopeResponse(BluOnXBase):
    id: UUID
    contract_id: UUID
    envelope_id: str
    status: str
    sent_at: datetime | None = None
    completed_at: datetime | None = None
    document_url: str | None = None
    webhook_payload: dict | None = None
    created_at: datetime
    updated_at: datetime
