"""
Pydantic models for the contract_signers table.

The roster of people authorized to sign contracts on behalf of BluOnX. One of
these is chosen per award (awards.signer_id) and becomes the DocuSign
routingOrder-1 recipient plus the printed name on the contract PDF.
"""

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr

from app.models.common import BluOnXBase


class ContractSignerCreate(BluOnXBase):
    full_name: str
    email: EmailStr
    title: str | None = None


class ContractSignerUpdate(BluOnXBase):
    # Every writable field must be declared here. The service applies the patch
    # with model_dump(exclude_unset=True), which silently drops anything the
    # model does not know about — an undeclared field would return 200 having
    # written nothing.
    full_name: str | None = None
    email: EmailStr | None = None
    title: str | None = None
    is_active: bool | None = None


class ContractSignerResponse(BluOnXBase):
    id: UUID
    full_name: str
    email: str
    title: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
