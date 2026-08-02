"""Bid package endpoints — /api/v1/bid-packages"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client
from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.bid_packages import (
    BidPackageCreateRequest,
    BidPackageCreateResponse,
    BidPackageDetailResponse,
    BidPackageListResponse,
    EmailLogResponse,
    InvitationListResponse,
)
from app.models.bids import (
    BidPackageCreate,
    BidPackageDocumentCreate,
    BidPackageDocumentResponse,
    BidPackageResponse,
    BidPackageUpdate,
    BidScoreCohortResponse,
)
from app.services.bid_package_service import (
    BidPackageValidationError,
    create_bid_package_with_invitations,
)
from app.services.bid_scoring_service import (
    BidScoringError,
    get_bid_package_scores,
    score_bid_package,
)
from app.services.bid_package_list_service import (
    BidPackageListValidationError,
    list_bid_packages as list_bid_packages_service,
)
from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    close_bidding,
    get_bid_package_detail,
    get_bid_package_email_log,
    list_invitations,
)
from app.services.email_service import EmailService, get_email_service
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/tasks/{task_id}/bid-packages",
    response_model=BidPackageCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bid_package_endpoint(
    task_id: UUID,
    body: BidPackageCreateRequest,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Create a bid package with invitations and send emails to vendors."""
    payload = {
        "task_id": str(task_id),
        "bid_template_id": str(body.bid_template_id),
        "deadline": body.deadline.isoformat(),
        "scope_of_work_document_id": str(body.scope_of_work_document_id),
        "project_document_ids": [str(d) for d in body.project_document_ids],
        "vendor_selections": [
            {
                "vendor_id": str(vs.vendor_id),
                "vendor_contact_id": str(vs.vendor_contact_id),
            }
            for vs in body.vendor_selections
        ],
    }
    if body.instructions is not None:
        payload["instructions"] = body.instructions
    # Date is serialized to "YYYY-MM-DD" for DB + email context.
    payload["desired_start_date"] = (
        body.desired_start_date.isoformat() if body.desired_start_date else None
    )

    try:
        result = await create_bid_package_with_invitations(
            task_id=task_id,
            payload=payload,
            created_by=user["user_id"],
            db=db,
            email_service=email_service,
            template_renderer=template_renderer,
        )
    except BidPackageValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return result


@router.get("/bid-packages", response_model=BidPackageListResponse)
async def list_bid_packages(
    status: str | None = None,
    project_id: UUID | None = None,
    sort_by: str = "deadline",
    sort_order: str = "asc",
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cross-project bid package list with denormalized project / task names
    and SQL-computed invitation counts."""
    try:
        items = await list_bid_packages_service(
            db=db,
            status=status,
            project_id=project_id,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except BidPackageListValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"items": items}


@router.get(
    "/bid-packages/{bid_package_id}",
    response_model=BidPackageDetailResponse,
)
async def get_bid_package(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a bid package with invitation summary, invitations, and documents.

    Applies lazy expiration: if the deadline has passed, outstanding
    invitations are marked 'expired' and the package is closed before
    the response is built.
    """
    try:
        return await get_bid_package_detail(bid_package_id=bid_package_id, db=db)
    except InvitationTrackingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/bid-packages/{bid_package_id}/close")
async def close_bid_package(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Manually close bidding early (open -> evaluating).

    Allowed only from 'open' (409 otherwise), before or after the deadline. This
    stops new bid inflow immediately (the vendor portal gates on status == 'open').
    In-flight revision tokens are unaffected — they are gated by their own
    revision_deadline, not the package status.
    """
    try:
        return await close_bidding(bid_package_id=bid_package_id, db=db)
    except InvitationTrackingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/bid-packages/{bid_package_id}/invitations",
    response_model=InvitationListResponse,
)
async def list_bid_package_invitations(
    bid_package_id: UUID,
    status: str | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List invitations for a bid package. Supports ?status=<filter>."""
    try:
        invitations = await list_invitations(
            bid_package_id=bid_package_id,
            status_filter=status,
            db=db,
        )
    except InvitationTrackingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"invitations": invitations}


@router.get(
    "/bid-packages/{bid_package_id}/email-log",
    response_model=EmailLogResponse,
)
async def get_bid_package_email_log_endpoint(
    bid_package_id: UUID,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Return one page of email_log rows referencing invitations in this package."""
    try:
        items, total = await get_bid_package_email_log(
            bid_package_id=bid_package_id, db=db, page=page, page_size=page_size
        )
    except InvitationTrackingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post(
    "/bid-packages/{bid_package_id}/scores",
    response_model=BidScoreCohortResponse,
)
async def compute_bid_package_scores(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Compute (or recompute) weighted scores for a competitive bid package's
    current submissions. Task 8.2."""
    try:
        return await score_bid_package(
            bid_package_id, scored_by=user["user_id"], db=db
        )
    except BidScoringError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/bid-packages/{bid_package_id}/scores",
    response_model=BidScoreCohortResponse,
)
async def read_bid_package_scores(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Read persisted weighted scores for a competitive bid package, joined to
    the live non-superseded cohort. Read-only — no recompute, no writes.
    Empty/never-computed returns 200 with scores:[]. Task 8.3/8.4 seam."""
    try:
        return await get_bid_package_scores(bid_package_id, db=db)
    except BidScoringError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/bid-packages", response_model=BidPackageResponse, status_code=status.HTTP_201_CREATED)
async def create_bid_package(
    bid_package: BidPackageCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new bid package for a task."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/bid-packages/{bid_package_id}", response_model=BidPackageResponse)
async def update_bid_package(
    bid_package_id: UUID,
    bid_package: BidPackageUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/bid-packages/{bid_package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bid_package(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cancel a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Bid Package Documents ────────────────────────────────────────────────


# NOTE: no `GET /bid-packages/{id}/documents` list route by design. Attached
# documents come back on the package detail response, and bid_package_documents
# is readable from Supabase under RLS. This was a stub returning `[]`, which a
# client could not distinguish from a package with no attachments.


@router.post(
    "/bid-packages/{bid_package_id}/documents",
    response_model=BidPackageDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_document_to_bid_package(
    bid_package_id: UUID,
    document: BidPackageDocumentCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Attach a project document to a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete(
    "/bid-packages/{bid_package_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_document_from_bid_package(
    bid_package_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Remove a document from a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")
