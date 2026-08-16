"""Contract signer endpoints — /api/v1/contract-signers

Writes only. There is no GET: the settings page and the award-screen dropdown
both read `contract_signers` directly from Supabase under
`contract_signers_select_authenticated`, which permits any active user to read
every row including inactive ones. Adding a read here would be a second path to
the same data.

There is no DELETE either. Revocation is `is_active = FALSE`; `awards.signer_id`
is ON DELETE RESTRICT and the roster is referenced by historical contracts.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.core.auth import require_admin
from app.core.supabase_client import get_supabase
from app.models.contract_signers import (
    ContractSignerCreate,
    ContractSignerResponse,
    ContractSignerUpdate,
)
from app.services import contract_signer_service

router = APIRouter()


@router.post(
    "/contract-signers",
    response_model=ContractSignerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract_signer(
    signer: ContractSignerCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Add someone to the BluOnX contract-signer roster (admin only).

    A collision on email returns 409. The message distinguishes a live duplicate
    from a previously deactivated entry, which the admin should reactivate
    instead.
    """
    return contract_signer_service.create_signer(db, signer)


@router.patch("/contract-signers/{signer_id}", response_model=ContractSignerResponse)
async def update_contract_signer(
    signer_id: UUID,
    patch: ContractSignerUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Edit a signer, or activate/deactivate one (admin only).

    Deactivating the only remaining active signer returns 409: no task could be
    awarded until one existed again.
    """
    return contract_signer_service.update_signer(db, signer_id, patch)
