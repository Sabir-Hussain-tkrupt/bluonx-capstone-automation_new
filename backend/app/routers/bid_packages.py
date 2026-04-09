"""Bid package endpoints — /api/v1/bid-packages"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.models.bid_packages import (
    BidPackageCreateRequest,
    BidPackageCreateResponse,
    BidPackageDetailResponse,
    EmailLogResponse,
    InvitationListResponse,
)
from app.models.bids import (
    BidPackageCreate,
    BidPackageDocumentCreate,
    BidPackageDocumentResponse,
    BidPackageResponse,
    BidPackageUpdate,
)
from app.services.bid_package_service import (
    BidPackageValidationError,
    create_bid_package_with_invitations,
)
from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    get_bid_package_detail,
    get_bid_package_email_log,
    list_invitations,
)
from app.services.email_service import EmailService
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_email_service(db: Client) -> EmailService:
    """Instantiate EmailService with the correct provider."""
    if settings.EMAIL_PROVIDER == "mock":
        from app.services.email_providers.mock_provider import MockEmailProvider

        provider = MockEmailProvider()
    else:
        from app.services.email_providers.ses_provider import SESEmailProvider

        provider = SESEmailProvider()
    return EmailService(provider=provider, db_client=db)


@router.post(
    "/tasks/{task_id}/bid-packages",
    response_model=BidPackageCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bid_package_endpoint(
    task_id: UUID,
    request: BidPackageCreateRequest,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a bid package with invitations and send emails to vendors."""
    email_service = _get_email_service(db)
    payload = {
        "task_id": str(task_id),
        "bid_template_id": str(request.bid_template_id),
        "deadline": request.deadline.isoformat(),
        "project_document_ids": [str(d) for d in request.project_document_ids],
        "vendor_selections": [
            {
                "vendor_id": str(vs.vendor_id),
                "vendor_contact_id": str(vs.vendor_contact_id),
            }
            for vs in request.vendor_selections
        ],
    }

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


@router.get("/bid-packages", response_model=list[BidPackageResponse])
async def list_bid_packages(
    task_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List bid packages, optionally filtered by task_id."""
    # TODO: Implement in later phase
    return []


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
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Return all email_log rows referencing invitations in this bid package."""
    try:
        items = await get_bid_package_email_log(bid_package_id=bid_package_id, db=db)
    except InvitationTrackingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"items": items}


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


@router.get(
    "/bid-packages/{bid_package_id}/documents",
    response_model=list[BidPackageDocumentResponse],
)
async def list_bid_package_documents(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List documents attached to a bid package."""
    # TODO: Implement in later phase
    return []


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
