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
from app.models.bids import BidRevisionRequestResponse
from app.models.vendor_portal import (
    AttachmentResponse,
    BidDraftModel,
    DeclineRevisionPayload,
    DraftPayload,
    RevisionPrefillResponse,
    SignedUrlResponse,
    SubmissionResponse,
    SubmitBidResponse,
    VendorBidContextModel,
)
from app.services.bid_revision_service import decline_revision_request
from app.services.email_service import EmailService, get_email_service
from app.services.template_renderer import template_renderer
from app.services.vendor_portal_service import (
    assert_package_open_and_before_deadline,
    assert_revision_request_active,
    build_bid_context,
    build_line_item_rows,
    build_revision_prefill,
    fetch_attachments,
    fetch_submission_detail,
    fetch_template_items_map,
    fetch_template_metadata,
    load_draft_response,
    resolve_unique_filename,
    send_revision_submitted_email,
    send_submission_confirmation_email,
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
            " total_amount, vendor_notes, proposed_start_date,"
            " sow_attested_name, sow_attested_at,"
            " submitted_at, updated_at"
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


def _resolve_package_sow_path(
    db: Client, bid_package_id: UUID, project_document_id: UUID
) -> str | None:
    """Return the SoW file_path iff `project_document_id` is this package's SoW.

    The SoW lives on `bid_packages.scope_of_work_document_id`, outside the
    `bid_package_documents` junction that gates reference docs. Returns None
    (→ 404 at the caller) when the doc is not this package's SoW, so a vendor
    can't probe for documents on other packages.

    Two explicit lookups (package → SoW id, then the doc by id) avoid a nested
    PostgREST embed, which would be ambiguous (bid_packages has both a direct
    FK to project_documents and a many-to-many via bid_package_documents).
    """
    pkg_resp = (
        db.table("bid_packages")
        .select("scope_of_work_document_id")
        .eq("id", str(bid_package_id))
        .eq("scope_of_work_document_id", str(project_document_id))
        .limit(1)
        .execute()
    )
    rows = pkg_resp.data or []
    if not rows:
        return None

    doc_resp = (
        db.table("project_documents")
        .select("file_path")
        .eq("id", str(project_document_id))
        .limit(1)
        .execute()
    )
    doc_rows = doc_resp.data or []
    return doc_rows[0].get("file_path") if doc_rows else None


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


def _resolve_revision_draft_target(
    db: Client, ctx: VendorContext
) -> tuple[str, int, str | None]:
    """Revision pre-flight shared by both create_draft 409 spots.

    Returns (original_submission_id, predecessor_revision_number,
    existing_revision_draft_id | None). Centralized so the pre-flight
    check and the UNIQUE-violation recovery branch stay identical.
    """
    rr_resp = (
        db.table("bid_revision_requests")
        .select("id, original_submission_id, status")
        .eq("id", str(ctx.bid_revision_request_id))
        .limit(1)
        .execute()
    )
    rr_rows = rr_resp.data or []
    if not rr_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revision request not found",
        )
    rr = rr_rows[0]
    if rr["status"] != "pending":
        # Defense-in-depth: assert_revision_request_active already
        # enforced this at the guard step.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This revision request is no longer active",
        )
    original_submission_id = str(rr["original_submission_id"])

    pred_resp = (
        db.table("bid_submissions")
        .select("revision_number")
        .eq("id", original_submission_id)
        .limit(1)
        .execute()
    )
    pred_rows = pred_resp.data or []
    if not pred_rows:
        # Unreachable: the revision request pins a finalized predecessor.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original submission not found",
        )
    predecessor_revision_number = pred_rows[0]["revision_number"]

    draft_resp = (
        db.table("bid_submissions")
        .select("id")
        .eq("bid_invitation_id", str(ctx.bid_invitation_id))
        .eq("is_draft", True)
        .eq("supersedes_submission_id", original_submission_id)
        .limit(1)
        .execute()
    )
    draft_rows = draft_resp.data or []
    existing_draft_id = draft_rows[0]["id"] if draft_rows else None
    return original_submission_id, predecessor_revision_number, existing_draft_id


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
    if ctx.bid_revision_request_id is None:
        assert_package_open_and_before_deadline(db, ctx.bid_package_id)
    else:
        # Revision tokens validate against the per-request deadline +
        # status, NOT the package deadline / package status.
        assert_revision_request_active(db, ctx.bid_revision_request_id)

    revision_original_id: str | None = None
    revision_number: int | None = None
    if ctx.bid_revision_request_id is None:
        # Initial bid: short-circuit if a submission already exists —
        # avoids a roundtrip to the UNIQUE-violation path on the common
        # case. The finalized predecessor of a revision is EXPECTED to
        # exist, so this 409 must not fire on the revision path.
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
    else:
        revision_original_id, predecessor_rev, existing_draft_id = (
            _resolve_revision_draft_target(db, ctx)
        )
        if existing_draft_id is not None:
            # Idempotent resume: vendor reopened the revision link.
            # Returns with the route's 201 (create-or-resume semantic).
            return load_draft_response(db, existing_draft_id)
        revision_number = predecessor_rev + 1

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
        "proposed_start_date": (
            payload.proposed_start_date.isoformat()
            if payload.proposed_start_date is not None
            else None
        ),
        # Attestation is saved on the draft but only stamped (sow_attested_at)
        # at submit. Never prefilled on a revision — the vendor re-types it.
        "sow_attested_name": payload.sow_attested_name,
        "status": "draft",
        "is_draft": True,
        "is_direct_assign": False,
    }
    if revision_original_id is not None:
        # fn_enforce_supersession_chain validates: predecessor exists,
        # same invitation, predecessor finalized, revision_number == +1.
        submission_row["supersedes_submission_id"] = revision_original_id
        submission_row["revision_number"] = revision_number
    try:
        insert_resp = (
            db.table("bid_submissions").insert(submission_row).execute()
        )
    except APIError as e:
        if _is_unique_violation(e):
            if ctx.bid_revision_request_id is None:
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
            else:
                # Effectively unreachable: the partial unique index
                # idx_bid_submissions_current_per_invitation excludes
                # drafts, so a revision-draft insert can't collide. If a
                # concurrent revision draft somehow exists, resume it.
                _, _, existing_draft_id = _resolve_revision_draft_target(db, ctx)
                if existing_draft_id is not None:
                    return load_draft_response(db, existing_draft_id)
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
    if ctx.bid_revision_request_id is None:
        assert_package_open_and_before_deadline(db, ctx.bid_package_id)
    else:
        # Revision draft edits validate against the revision request, not
        # the (now-closed) package deadline / status.
        assert_revision_request_active(db, ctx.bid_revision_request_id)

    template_id = await _fetch_template_id_for_invitation(db, ctx.bid_invitation_id)
    template_map = fetch_template_items_map(db, template_id)

    # Update scalar fields. updated_at auto-refreshes via trg_bid_submissions_updated_at.
    db.table("bid_submissions").update(
        {
            "total_amount": (
                str(payload.total_amount) if payload.total_amount is not None else None
            ),
            "vendor_notes": payload.vendor_notes,
            "proposed_start_date": (
                payload.proposed_start_date.isoformat()
                if payload.proposed_start_date is not None
                else None
            ),
            # Persisted on autosave; the finalize stamp (sow_attested_at) is
            # set only at submit.
            "sow_attested_name": payload.sow_attested_name,
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
    email_service: EmailService = Depends(get_email_service),
) -> SubmitBidResponse:
    """Finalize a draft: run validation, set status='submitted', send receipt.

    The trigger `fn_sync_bid_invitation_on_submission` auto-syncs
    bid_invitations.status and responded_at — we do not touch that table
    here.

    Confirmation email is best-effort: a provider failure after the DB
    update still returns 200. The bid is committed, and the response's
    `confirmation_email_sent` flag tells the UI whether to soften the
    "email has been sent" copy. Re-sending is an ops concern, not a
    vendor-workflow concern.
    """
    sub = _fetch_owned_submission(db, ctx, submission_id)
    _assert_draft(sub)
    if ctx.bid_revision_request_id is None:
        assert_package_open_and_before_deadline(db, ctx.bid_package_id)
    else:
        # Revision tokens validate against the per-request deadline +
        # status, NOT the package deadline / package status.
        assert_revision_request_active(db, ctx.bid_revision_request_id)

    # Re-read authoritative state (NEVER trust the request body for
    # validation — drafts are the source of truth for submit-time checks).
    template_id = await _fetch_template_id_for_invitation(db, ctx.bid_invitation_id)
    template_meta = fetch_template_metadata(db, template_id)
    template_items = list(fetch_template_items_map(db, template_id).values())

    # Task 8.1.5: timeline rule — proposed_start_date is required iff the
    # package has a desired_start_date. Read the package row directly so
    # this works on both the initial and revision branches (revisions
    # inherit the package's desired date — it stays pinned on rebid).
    pkg_resp = (
        db.table("bid_packages")
        .select("desired_start_date")
        .eq("id", str(ctx.bid_package_id))
        .single()
        .execute()
    )
    pkg_data = pkg_resp.data or {}
    if isinstance(pkg_data, list):
        pkg_data = pkg_data[0] if pkg_data else {}
    package_has_desired_date = bool(pkg_data.get("desired_start_date"))

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
        package_has_desired_date=package_has_desired_date,
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
                # Server-stamp the attestation timestamp ONLY at finalize —
                # never on draft create/autosave. This is what realizes onto
                # contracts.sow_signed_date at envelope-send.
                "sow_attested_at": submitted_at.isoformat(),
            }
        )
        .eq("id", str(submission_id))
        .eq("is_draft", True)
        .execute()
    )
    if not update_resp.data:
        # is_draft in the WHERE makes this also catch the TOCTOU race
        # between _assert_draft and this UPDATE. Spec-mandated
        # defense-in-depth: previously a (today-unreachable) 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bid has already been submitted",
        )

    # The total_amount returned to the client / logged in the email must
    # come from the persisted submission, not the pre-submit snapshot —
    # the validator may have recomputed it.
    committed = update_resp.data[0]
    committed_total = committed.get("total_amount")

    # Gather context for the response + email. One focused read instead of
    # rebuilding the full bid-context object (which also hydrates the
    # template and project documents we don't need here).
    email_ctx = _fetch_submission_email_context(db, submission_id)
    attachment_count = _count_attachments(db, submission_id)

    # A revised submission gets the revision receipt; an initial bid gets
    # the (unchanged, bit-identical) confirmation. Never both — the
    # discriminator is the revision claim already on the vendor JWT.
    if ctx.bid_revision_request_id is not None:
        email_sent = await send_revision_submitted_email(
            email_service=email_service,
            template_renderer=template_renderer,
            submission_id=submission_id,
            submitted_at=submitted_at,
            total_amount=committed_total,
            attachment_count=attachment_count,
            context=email_ctx,
        )
    else:
        email_sent = await send_submission_confirmation_email(
            email_service=email_service,
            template_renderer=template_renderer,
            submission_id=submission_id,
            submitted_at=submitted_at,
            total_amount=committed_total,
            attachment_count=attachment_count,
            context=email_ctx,
        )

    return SubmitBidResponse(
        id=submission_id,
        submitted_at=submitted_at,
        total_amount=committed_total,
        vendor_email=email_ctx["vendor_email"],
        vendor_company_name=email_ctx["vendor_company_name"],
        project_name=email_ctx["project_name"],
        task_name=email_ctx["task_name"],
        attachment_count=attachment_count,
        confirmation_email_sent=email_sent,
    )


@router.get(
    "/submissions/{submission_id}/revision-prefill",
    response_model=RevisionPrefillResponse,
    status_code=status.HTTP_200_OK,
)
async def get_revision_prefill(
    submission_id: UUID,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> RevisionPrefillResponse:
    """Original submission's data, shaped for the revision form prefill.

    Revision-only: requires a revision JWT AND the path submission_id
    must equal the revision request's original_submission_id AND the JWT
    vendor must own the submission. Vendor identity comes from the JWT,
    never from the request.
    """
    if ctx.bid_revision_request_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for revision requests",
        )

    rr_resp = (
        db.table("bid_revision_requests")
        .select("id, original_submission_id")
        .eq("id", str(ctx.bid_revision_request_id))
        .limit(1)
        .execute()
    )
    rr_rows = rr_resp.data or []
    if not rr_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revision request not found",
        )
    if str(rr_rows[0]["original_submission_id"]) != str(submission_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Submission does not match this revision request",
        )

    sub_resp = (
        db.table("bid_submissions")
        .select("vendor_id")
        .eq("id", str(submission_id))
        .limit(1)
        .execute()
    )
    sub_rows = sub_resp.data or []
    if not sub_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    if str(sub_rows[0]["vendor_id"]) != str(ctx.vendor_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Submission does not belong to this vendor",
        )

    template_id = await _fetch_template_id_for_invitation(
        db, ctx.bid_invitation_id
    )
    return build_revision_prefill(db, submission_id, template_id)


@router.post(
    "/revision-requests/{revision_request_id}/decline",
    response_model=BidRevisionRequestResponse,
    status_code=status.HTTP_200_OK,
)
async def decline_revision_request_endpoint(
    revision_request_id: UUID,
    payload: DeclineRevisionPayload,
    ctx: VendorContext = Depends(get_vendor_context),
    db: Client = Depends(get_supabase),
) -> BidRevisionRequestResponse:
    """Vendor declines a pending revision request from the SPA.

    Revision-only: requires a revision JWT AND the JWT's
    bid_revision_request_id claim must equal the path id. A vendor must not
    be able to decline another vendor's request. Identity comes from the
    JWT, never the request body or URL.
    """
    if ctx.bid_revision_request_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available for revision requests",
        )
    if str(ctx.bid_revision_request_id) != str(revision_request_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This token does not match this revision request",
        )

    # A blank / whitespace-only textarea must persist as SQL NULL, not "".
    reason = (payload.decline_reason or "").strip() or None

    return decline_revision_request(
        db,
        revision_request_id=revision_request_id,
        decline_reason=reason,
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
    file_path: str | None = None
    if rows and rows[0].get("project_documents"):
        file_path = rows[0]["project_documents"]["file_path"]
    else:
        # The Scope of Work is pinned on the package via
        # bid_packages.scope_of_work_document_id, NOT the bid_package_documents
        # junction — so allow it here when the requested doc is this package's SoW.
        file_path = _resolve_package_sow_path(db, ctx.bid_package_id, project_document_id)

    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this bid package",
        )
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


def _fetch_submission_email_context(db: Client, submission_id: UUID) -> dict:
    """One joined read → all fields the confirmation email + response need.

    Deliberately narrower than build_bid_context: skips template items,
    project documents, and the existing-draft hydrate (none are useful
    post-submit, and those fetches are not free).
    """
    resp = (
        db.table("bid_submissions")
        .select(
            "id,"
            " bid_invitations!inner("
            "   vendor_contacts(full_name, email),"
            "   vendors(company_name),"
            "   bid_packages!inner("
            "     created_by,"
            "     tasks!inner("
            "       name,"
            "       projects(name)"
            "     )"
            "   )"
            " )"
        )
        .eq("id", str(submission_id))
        .single()
        .execute()
    )
    if not resp.data:
        # Unreachable: caller just updated this row. Defensive 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    inv = resp.data["bid_invitations"]
    contact = inv.get("vendor_contacts") or {}
    vendor = inv.get("vendors") or {}
    pkg = inv["bid_packages"]
    task = pkg["tasks"]
    project = task.get("projects") or {}

    # PM = bid_packages.created_by. Separate fetch keeps the join above
    # simple (single-FK ambiguity on public.users otherwise) and the PM
    # lookup is optional — a missing user doesn't fail the email.
    pm_name: str | None = None
    pm_email: str | None = None
    pm_id = pkg.get("created_by")
    if pm_id:
        pm_resp = (
            db.table("users")
            .select("full_name, email")
            .eq("id", str(pm_id))
            .limit(1)
            .execute()
        )
        pm_rows = pm_resp.data or []
        if pm_rows:
            pm_name = pm_rows[0].get("full_name")
            pm_email = pm_rows[0].get("email")

    return {
        "vendor_contact_name": contact.get("full_name") or "",
        "vendor_email": contact.get("email") or "",
        "vendor_company_name": vendor.get("company_name") or "",
        "project_name": project.get("name") or "",
        "task_name": task.get("name") or "",
        "pm_name": pm_name,
        "pm_email": pm_email,
    }


def _count_attachments(db: Client, submission_id: UUID) -> int:
    resp = (
        db.table("bid_attachments")
        .select("id", count="exact")
        .eq("bid_submission_id", str(submission_id))
        .execute()
    )
    return getattr(resp, "count", None) or 0
