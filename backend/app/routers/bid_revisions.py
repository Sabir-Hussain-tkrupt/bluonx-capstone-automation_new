"""PM bid-revision endpoints — /api/v1/bid-revision-requests

Per-vendor bid revision, Step 2 (PM side). Cancel is POST /{id}/cancel (a
state transition, not a DELETE). List filters by bid_package_id, matching
the flat GET /bid-packages list convention.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.bids import (
    BidRevisionRequestCreate,
    BidRevisionRequestCreateResponse,
    BidRevisionRequestResponse,
)
from app.services.bid_revision_service import (
    BidRevisionValidationError,
    cancel_revision_request,
    create_revision_request,
    list_revision_requests_for_package,
    send_revision_request_email,
)
from app.services.email_service import EmailService, get_email_service
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/bid-revision-requests",
    response_model=BidRevisionRequestCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_revision_request_endpoint(
    body: BidRevisionRequestCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
) -> BidRevisionRequestCreateResponse:
    """PM asks one vendor to revise their submitted bid."""
    try:
        result = create_revision_request(
            db, payload=body, requested_by=user["user_id"]
        )
    except BidRevisionValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc

    # Best-effort vendor notification — the request is already committed,
    # so a send failure must never turn the 201 into an error. The helper
    # swallows its own exceptions; this guard is defence-in-depth.
    try:
        rr = result.revision_request
        await send_revision_request_email(
            email_service=email_service,
            template_renderer=template_renderer,
            db=db,
            bid_invitation_id=rr.bid_invitation_id,
            revision_request_id=rr.id,
            pm_note=rr.pm_note,
            revision_deadline=rr.revision_deadline,
            portal_url=result.portal_url,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Revision-request email dispatch raised for %s", result.revision_request.id
        )

    return result


@router.post(
    "/bid-revision-requests/{revision_request_id}/cancel",
    response_model=BidRevisionRequestResponse,
)
async def cancel_revision_request_endpoint(
    revision_request_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
) -> BidRevisionRequestResponse:
    """PM cancels a still-pending revision request (revokes its magic link)."""
    try:
        return cancel_revision_request(
            db,
            revision_request_id=revision_request_id,
            cancelled_by=user["user_id"],
        )
    except BidRevisionValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.get(
    "/bid-revision-requests",
    response_model=list[BidRevisionRequestResponse],
)
async def list_revision_requests_endpoint(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
) -> list[BidRevisionRequestResponse]:
    """All revision requests for a bid package, newest first."""
    return list_revision_requests_for_package(
        db, bid_package_id=bid_package_id
    )
