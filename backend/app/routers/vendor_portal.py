"""
Vendor portal submission / attachment / download endpoints (Tasks 5.3–5.6).

All endpoints here authenticate via the vendor JWT (`get_vendor_context`).
Client-supplied `vendor_id` / `bid_invitation_id` are never trusted — they
are resolved server-side from the JWT context. The DB trigger
`fn_enforce_submission_vendor_consistency` is a backstop, not the gate.

Shared guard order on every write endpoint (keep this consistent across all
handlers — diverging order has subtle security implications):
  1. get_vendor_context              → 401 if JWT bad
  2. ownership check                 → 404 if submission isn't this vendor's
  3. draft-state check               → 409 if already submitted
  4. package open + deadline check   → 423 if closed / past deadline
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from postgrest.exceptions import APIError
from supabase import Client

from app.core.file_validation import sanitize_filename, validate_upload
from app.core.storage import delete_file, get_signed_url, upload_file
from app.core.supabase_client import get_supabase
from app.core.vendor_auth import VendorContext, get_vendor_context
from app.models.vendor_portal import (
    AttachmentResponse,
    BidDraftModel,
    DraftPayload,
    SignedUrlResponse,
    SubmissionResponse,
    SubmitBidResponse,
    VendorBidContextModel,
)
from app.services.vendor_portal_service import (
    assert_package_open_and_before_deadline,
    build_bid_context,
    build_line_item_rows,
    fetch_attachments,
    fetch_submission_detail,
    fetch_template_items_map,
    fetch_template_metadata,
    load_draft_response,
    resolve_unique_filename,
)
from app.services.vendor_portal_submit_validator import validate_for_submit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vendor-portal")

BID_ATTACHMENTS_BUCKET = "bid-attachments"
PROJECT_DOCUMENTS_BUCKET = "project-documents"

# Spec max for vendor attachments is 10MB even though the bucket config
# permits 50MB for dev. Enforce at the router layer.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

SIGNED_URL_EXPIRY_SECONDS = 3600


# ── Internal guards ──────────────────────────────────────────────────────


def _fetch_owned_submission(
    db: Client, ctx: VendorContext, submission_id: UUID
) -> dict:
    """Return the submission row iff it belongs to this vendor's invitation.

    Always filter by ctx.bid_invitation_id — defense-in-depth against a
    vendor sending another vendor's submission id. We return 404 rather
    than 403 so the endpoint never leaks which submissions exist.
    """
    resp = (
        db.table("bid_submissions")
        .select(
            "id, bid_invitation_id, vendor_id, status, is_draft,"
            " total_amount, vendor_notes, submitted_at, updated_at"
        )
        .eq("id", str(submission_id))
        .eq("bid_invitation_id", str(ctx.bid_invitation_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    sub = rows[0]
    if str(sub["vendor_id"]) != str(ctx.vendor_id):
        # Trigger would catch this too, but don't let the request even begin.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    return sub


def _assert_draft(sub: dict) -> None:
    if not sub.get("is_draft"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bid has already been submitted and can no longer be edited",
        )


def _find_existing_submission(db: Client, bid_invitation_id: UUID) -> dict | None:
    resp = (
        db.table("bid_submissions")
        .select("id, is_draft")
        .eq("bid_invitation_id", str(bid_invitation_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _is_unique_violation(err: APIError) -> bool:
    """Heuristic — supabase-py wraps Postgres errors in APIError with code.

    Unique-violation in Postgres is SQLSTATE 23505. postgrest surfaces
    this as `.code == "23505"` or a message containing "duplicate key".
    """
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23505" or "duplicate key" in msg or "unique" in msg


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get(
    "/bid-context",
    response_model=VendorBidContextModel,
    status_code=status.HTTP_200_OK,
)
async def get_bid_context(
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> VendorBidContextModel:
    """Re-fetch the full bid context for the current vendor session.

    Same payload shape as the `bid_context` returned by
    POST /vendor-auth/validate-token. The portal calls this after long
    idle periods or when it needs fresh draft/attachment state.
    """
    return build_bid_context(db, ctx.bid_invitation_id)


@router.post(
    "/submissions",
    response_model=BidDraftModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_draft(
    payload: DraftPayload,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> BidDraftModel:
    """Create a new draft submission.

    Idempotent on the UNIQUE(bid_invitation_id) constraint — a second POST
    (from an auto-save race or a retried request) returns 409 with the
    existing submission id so the frontend can switch to PUT.
    """
    assert_package_open_and_before_deadline(db, ctx.bid_package_id)

    # Short-circuit if a submission already exists — avoids a roundtrip to
    # the UNIQUE-violation path on the common case.
    existing = _find_existing_submission(db, ctx.bid_invitation_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": (
                    "Draft already exists"
                    if existing["is_draft"]
                    else "Bid already submitted"
                ),
                "existing_submission_id": existing["id"],
            },
        )

    # Fetch template to copy description/item_type/uom/sort_order into the
    # line-item rows. This decouples the submission from future template
    # edits (Task 5.4 contract).
    template_id = await _fetch_template_id_for_invitation(db, ctx.bid_invitation_id)
    template_map = fetch_template_items_map(db, template_id)

    # Insert the submission row. The DB trigger enforces vendor_id matches
    # the invitation — a defensive backstop should something slip through
    # here. Our own code resolves vendor_id from ctx, never from body.
    submission_row = {
        "bid_invitation_id": str(ctx.bid_invitation_id),
        "vendor_id": str(ctx.vendor_id),
        "total_amount": (
            str(payload.total_amount) if payload.total_amount is not None else None
        ),
        "vendor_notes": payload.vendor_notes,
        "status": "draft",
        "is_draft": True,
        "is_direct_assign": False,
    }
    try:
        insert_resp = (
            db.table("bid_submissions").insert(submission_row).execute()
        )
    except APIError as e:
        if _is_unique_violation(e):
            existing = _find_existing_submission(db, ctx.bid_invitation_id)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "detail": (
                            "Draft already exists"
                            if existing["is_draft"]
                            else "Bid already submitted"
                        ),
                        "existing_submission_id": existing["id"],
                    },
                ) from e
        logger.exception("bid_submissions insert failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create draft",
        ) from e

    if not insert_resp.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create draft",
        )
    submission_id = insert_resp.data[0]["id"]

    # Insert line items. On failure, delete the submission we just created
    # so we never leave an orphan draft with no line_items backing it.
    try:
        rows = build_line_item_rows(payload.line_items, template_map, submission_id)
        if rows:
            db.table("bid_line_items").insert(rows).execute()
    except HTTPException:
        db.table("bid_submissions").delete().eq("id", submission_id).execute()
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("bid_line_items insert failed; rolling back submission")
        db.table("bid_submissions").delete().eq("id", submission_id).execute()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create draft line items",
        ) from e

    return load_draft_response(db, submission_id)


@router.put(
    "/submissions/{submission_id}",
    response_model=BidDraftModel,
    status_code=status.HTTP_200_OK,
)
async def update_draft(
    submission_id: UUID,
    payload: DraftPayload,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> BidDraftModel:
    """Update an existing draft.

    Replaces all line items (delete + re-insert). Not atomic across the two
    statements, but PUT is idempotent — the next auto-save restores state
    if anything interrupts. For a draft this is safer than diffing rows.
    """
    sub = _fetch_owned_submission(db, ctx, submission_id)
    _assert_draft(sub)
    assert_package_open_and_before_deadline(db, ctx.bid_package_id)

    template_id = await _fetch_template_id_for_invitation(db, ctx.bid_invitation_id)
    template_map = fetch_template_items_map(db, template_id)

    # Update scalar fields. updated_at auto-refreshes via trg_bid_submissions_updated_at.
    db.table("bid_submissions").update(
        {
            "total_amount": (
                str(payload.total_amount) if payload.total_amount is not None else None
            ),
            "vendor_notes": payload.vendor_notes,
        }
    ).eq("id", str(submission_id)).execute()

    # Replace line items: delete + insert. supabase-py has no transaction
    # support; see module docstring on atomicity trade-offs for drafts.
    db.table("bid_line_items").delete().eq(
        "bid_submission_id", str(submission_id)
    ).execute()

    rows = build_line_item_rows(payload.line_items, template_map, str(submission_id))
    if rows:
        db.table("bid_line_items").insert(rows).execute()

    return load_draft_response(db, str(submission_id))


@router.post(
    "/submissions/{submission_id}/submit",
    response_model=SubmitBidResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_bid(
    submission_id: UUID,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> SubmitBidResponse:
    """Finalize a draft: run validation, set status='submitted'.

    The trigger `fn_sync_bid_invitation_on_submission` auto-syncs
    bid_invitations.status and responded_at — we do not touch that table
    here.

    Confirmation email + PDF receipt are deferred to Task 5.7; TODOs mark
    where they plug in.
    """
    sub = _fetch_owned_submission(db, ctx, submission_id)
    _assert_draft(sub)
    assert_package_open_and_before_deadline(db, ctx.bid_package_id)

    # Re-read authoritative state (NEVER trust the request body for
    # validation — drafts are the source of truth for submit-time checks).
    template_id = await _fetch_template_id_for_invitation(db, ctx.bid_invitation_id)
    template_meta = fetch_template_metadata(db, template_id)
    template_items = list(fetch_template_items_map(db, template_id).values())

    li_resp = (
        db.table("bid_line_items")
        .select(
            "id, description, item_type, quantity, unit_price,"
            " lump_sum_amount, line_total, sort_order"
        )
        .eq("bid_submission_id", str(submission_id))
        .order("sort_order")
        .execute()
    )
    line_items = li_resp.data or []

    errors = validate_for_submit(
        submission=sub,
        line_items=line_items,
        template_items=template_items,
        is_lump_sum_template=bool(template_meta["is_lump_sum"]),
    )
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Submission failed validation",
                "errors": [e.model_dump() for e in errors],
            },
        )

    submitted_at = datetime.now(timezone.utc)
    update_resp = (
        db.table("bid_submissions")
        .update(
            {
                "is_draft": False,
                "status": "submitted",
                "submitted_at": submitted_at.isoformat(),
            }
        )
        .eq("id", str(submission_id))
        .execute()
    )
    if not update_resp.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize submission",
        )

    confirmation_number = _generate_confirmation_number(db, submitted_at.year)

    # TODO(Task 5.7): send confirmation email via EmailService + log in email_log.
    # TODO(Task 5.7): generate PDF receipt with reportlab/weasyprint, upload to
    #   bid-attachments/{submission_id}/receipt.pdf, expose via separate endpoint.

    return SubmitBidResponse(
        id=submission_id,
        confirmation_number=confirmation_number,
        submitted_at=submitted_at,
    )


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionResponse,
    status_code=status.HTTP_200_OK,
)
async def get_submission(
    submission_id: UUID,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> SubmissionResponse:
    """Read a submission (draft or final) plus its line items and attachments."""
    _fetch_owned_submission(db, ctx, submission_id)
    return fetch_submission_detail(db, str(submission_id))


@router.get(
    "/documents/{project_document_id}/download",
    response_model=SignedUrlResponse,
    status_code=status.HTTP_200_OK,
)
async def download_project_document(
    project_document_id: UUID,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> SignedUrlResponse:
    """Generate a signed URL for a project document attached to this bid package.

    The `bid_package_documents` junction is the authority for what's in
    scope — if the document isn't linked to this package, return 404 so
    the vendor can't probe for documents on other packages.
    """
    resp = (
        db.table("bid_package_documents")
        .select("project_documents(id, file_path)")
        .eq("bid_package_id", str(ctx.bid_package_id))
        .eq("project_document_id", str(project_document_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows or not rows[0].get("project_documents"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this bid package",
        )
    file_path = rows[0]["project_documents"]["file_path"]
    url = get_signed_url(db, PROJECT_DOCUMENTS_BUCKET, file_path, SIGNED_URL_EXPIRY_SECONDS)
    return SignedUrlResponse(url=url, expires_in=SIGNED_URL_EXPIRY_SECONDS)


@router.post(
    "/submissions/{submission_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    submission_id: UUID,
    file: UploadFile = File(...),
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> AttachmentResponse:
    """Upload a single attachment to a draft submission.

    On DB insert failure after a successful storage upload, the stored
    blob is deleted to avoid orphans — otherwise bid-attachments would
    accumulate files with no DB row pointing at them.
    """
    sub = _fetch_owned_submission(db, ctx, submission_id)
    _assert_draft(sub)
    assert_package_open_and_before_deadline(db, ctx.bid_package_id)

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    # Hard 10MB cap at router layer (spec), even though bucket config is
    # 50MB for dev convenience.
    if len(file_bytes) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File exceeds the 10MB size limit.",
        )

    content_type = file.content_type or "application/octet-stream"
    filename = sanitize_filename(file.filename or "attachment")
    validate_upload(file_bytes, filename, content_type, BID_ATTACHMENTS_BUCKET)

    folder = str(submission_id)
    resolved = resolve_unique_filename(db, BID_ATTACHMENTS_BUCKET, folder, filename)
    storage_path = f"{folder}/{resolved}"
    upload_file(db, BID_ATTACHMENTS_BUCKET, storage_path, file_bytes, content_type)

    try:
        insert_resp = (
            db.table("bid_attachments")
            .insert(
                {
                    "bid_submission_id": str(submission_id),
                    "file_name": resolved,
                    "file_path": storage_path,
                    "file_type": content_type,
                    "file_size": len(file_bytes),
                }
            )
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("bid_attachments insert failed; removing orphan storage blob")
        delete_file(db, BID_ATTACHMENTS_BUCKET, storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record attachment",
        ) from e

    if not insert_resp.data:
        delete_file(db, BID_ATTACHMENTS_BUCKET, storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record attachment",
        )

    row = insert_resp.data[0]
    return AttachmentResponse(
        id=row["id"],
        file_name=row["file_name"],
        file_size=row["file_size"],
        file_type=row.get("file_type"),
        uploaded_at=row["uploaded_at"],
    )


@router.delete(
    "/submissions/{submission_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment(
    submission_id: UUID,
    attachment_id: UUID,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> Response:
    sub = _fetch_owned_submission(db, ctx, submission_id)
    _assert_draft(sub)
    assert_package_open_and_before_deadline(db, ctx.bid_package_id)

    resp = (
        db.table("bid_attachments")
        .select("id, file_path, bid_submission_id")
        .eq("id", str(attachment_id))
        .eq("bid_submission_id", str(submission_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )
    attachment = rows[0]

    # DB first: if the delete fails, the storage object stays (safer than
    # the reverse, which would leave a dangling DB row pointing at a
    # missing blob).
    db.table("bid_attachments").delete().eq("id", str(attachment_id)).execute()
    delete_file(db, BID_ATTACHMENTS_BUCKET, attachment["file_path"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/submissions/{submission_id}/attachments",
    response_model=list[AttachmentResponse],
    status_code=status.HTTP_200_OK,
)
async def list_attachments(
    submission_id: UUID,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> list[AttachmentResponse]:
    _fetch_owned_submission(db, ctx, submission_id)
    return fetch_attachments(db, str(submission_id))


# ── Helpers ──────────────────────────────────────────────────────────────


async def _fetch_template_id_for_invitation(
    db: Client, bid_invitation_id: UUID
) -> str:
    """Look up the bid_template_id for this invitation's package.

    Used by POST/PUT/submit to copy template fields into line items and
    load is_lump_sum at submit time.
    """
    resp = (
        db.table("bid_invitations")
        .select("bid_packages(bid_template_id)")
        .eq("id", str(bid_invitation_id))
        .single()
        .execute()
    )
    pkg = (resp.data or {}).get("bid_packages") or {}
    template_id = pkg.get("bid_template_id")
    if not template_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bid package has no template configured",
        )
    return template_id


def _generate_confirmation_number(db: Client, year: int) -> str:
    """BID-{YYYY}-{seq:04d}, where seq = count of same-year submitted bids + 1.

    Display-only for now — the schema has no `confirmation_number` column.
    A small race window exists if two vendors finalize in the same second;
    acceptable while this value is not persisted or used for lookup.

    TODO(Task 5.7): persist to a new column (and ideally a Postgres
    sequence) so the number is stable and looking-up friendly.
    """
    jan_first = f"{year}-01-01T00:00:00+00:00"
    resp = (
        db.table("bid_submissions")
        .select("id", count="exact")
        .eq("status", "submitted")
        .gte("submitted_at", jan_first)
        .execute()
    )
    count = getattr(resp, "count", None) or 0
    return f"BID-{year}-{(count + 1):04d}"
