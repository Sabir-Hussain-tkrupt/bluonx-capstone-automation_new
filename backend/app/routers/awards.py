"""Award endpoints — /api/v1/awards"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.awards import (
    AwardCreateRequest,
    AwardResponse,
    AwardUpdate,
    PreAwardValidationResult,
)
from app.services.award_service import AwardError, create_award as create_award_service
from app.services.pre_award_validation_service import (
    PreAwardError,
    load_pre_award_context,
    validate_pre_award,
)

router = APIRouter()


@router.get(
    "/awards/validate/{bid_submission_id}",
    response_model=PreAwardValidationResult,
)
async def preview_pre_award_validation(
    bid_submission_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Read-only pre-award validation preview for a candidate submission (Task 9.1).

    Resolves the context server-side from the submission id and returns the
    structured pass/warn/block result so the PM sees what awarding would flag
    *before* committing. No side effects, no write. A blocking result is a
    200 with the block detail (the 422 hard-reject belongs to award-create in
    9.2/9.5); 404 on an unknown submission.
    """
    try:
        context = await load_pre_award_context(bid_submission_id, db=db)
    except PreAwardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return validate_pre_award(context)


# NOTE: there is deliberately no `GET /awards` list route. Awards are read
# straight from Supabase by the frontend under RLS (the hybrid data-access
# pattern: reads via Supabase, writes via FastAPI), so a list endpoint here
# would be redundant. It previously existed as a stub returning `[]`, which a
# client could not distinguish from "this task has no awards".


@router.get("/awards/{award_id}", response_model=AwardResponse)
async def get_award(
    award_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single award by ID."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/awards", response_model=AwardResponse, status_code=status.HTTP_201_CREATED)
async def create_award(
    award: AwardCreateRequest,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create an award for a bid submission (Task 9.2).

    Recomputes the Task 9.1 pre-award validation fresh server-side and gates the
    write: a `block` check → 422 (not overridable); a `warn` check requires
    `has_override` + a non-empty justification, else 422 returning the full
    result so the override dialog can render it. award_amount / task_id /
    vendor_id / awarded_by are server-derived; the award is written at
    `pending_acceptance` and the task flipped to `awarded`. The old superseded
    409 guard is subsumed by the validator's submission_eligibility block, with
    the DB trigger fn_enforce_award_consistency as defense-in-depth.
    """
    try:
        return await create_award_service(
            bid_submission_id=award.bid_submission_id,
            has_override=award.has_override,
            override_justification=award.override_justification,
            instructions=award.instructions,
            contract_valid_days=award.contract_valid_days,
            work_duration_days=award.work_duration_days,
            signer_id=award.signer_id,
            awarded_by=user["user_id"],
            db=db,
        )
    except (AwardError, PreAwardError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/awards/{award_id}/send-contract", status_code=status.HTTP_200_OK)
async def resend_contract_envelope(
    award_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Manually (re)send the contract envelope for an award (Task 9.3b).

    The post-commit send at award-create is best-effort; if it failed (DocuSign
    down, missing config) the award sits at `pending_acceptance` with no envelope.
    This re-runs the same re-entrant send path: it reuses an existing contract /
    envelope rather than duplicating, so it's safe to call repeatedly.
    """
    from app.services.contract_envelope_service import (
        ContractEnvelopeError,
        send_contract_envelope,
    )

    try:
        envelope = await send_contract_envelope(award_id, db=db)
    except ContractEnvelopeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {
        "envelope_id": envelope.get("envelope_id"),
        "status": envelope.get("status"),
        "contract_id": envelope.get("contract_id"),
    }


@router.patch("/awards/{award_id}", response_model=AwardResponse)
async def update_award(
    award_id: UUID,
    award: AwardUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update an award (e.g., status change)."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/awards/{award_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_award(
    award_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cancel an award."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")
