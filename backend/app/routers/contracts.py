"""Contract endpoints — /api/v1/contracts"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.awards import ContractCreate, ContractResponse, ContractUpdate
from app.models.reviews import ReviewCreate, ReviewResponse
from app.services import contract_service, review_service
from app.services.contract_service import ContractError
from app.services.review_service import ReviewError

router = APIRouter()


@router.get("/contracts", response_model=list[ContractResponse])
async def list_contracts(
    task_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List contracts, optionally filtered by task_id."""
    # TODO: Implement in later phase
    return []


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single contract by ID."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/contracts", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    contract: ContractCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a contract from an accepted award."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/contracts/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: UUID,
    contract: ContractUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a contract."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Terminate a contract."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/contracts/{contract_id}/mark-complete", response_model=ContractResponse)
async def mark_contract_complete(
    contract_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Mark a contract's work complete → status `completed`.

    Gated by the row-locked `fn_mark_contract_complete` RPC: refuses (409) while any
    milestone is still open, or when the contract is already complete / terminated.
    Surfaces the just-completed vendor rating flow on the frontend."""
    try:
        return contract_service.mark_contract_completed(str(contract_id), db=db)
    except ContractError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/contracts/{contract_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract_review(
    contract_id: UUID,
    review: ReviewCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Record the one PM performance rating (1-5) for a completed contract.

    vendor_id and reviewer are resolved server-side; only the rating and notes come
    from the client. 409 if the contract is not completed or already reviewed."""
    try:
        return review_service.create_review(
            contract_id=str(contract_id),
            rating=review.rating,
            notes=review.notes,
            reviewed_by=user["user_id"],
            db=db,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
