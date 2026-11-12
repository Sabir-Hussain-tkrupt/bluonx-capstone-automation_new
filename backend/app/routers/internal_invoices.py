"""Internal invoice endpoints — /api/v1/projects/{id}/invoices, /invoices/{id}

Who: field managers, office staff (project managers / admins) and finance.
`require_roles` is the real gate (service_role bypasses RLS). Visibility is
narrowed in the service: finance / executive / admin see every invoice, other
uploaders only their own.

Upload follows the project-documents flow exactly: read_upload → validate_upload
(extension, size, file signature) → upload to the private finance-documents
bucket → insert row; downloads are 1-hour signed URLs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.core.auth import require_roles
from app.core.file_validation import read_upload, sanitize_filename, validate_upload
from app.core.supabase_client import get_supabase
from app.models.common import SignedUrlResponse
from app.models.internal_invoices import (
    CategoriseResult,
    InvoiceCategorise,
    InvoiceResponse,
    InvoiceUpdate,
)
from app.services import internal_invoice_service as svc
from app.services.financial_errors import FinancialError

router = APIRouter()

INVOICE_ROLES = ("field_manager", "finance", "project_manager")
require_invoice_role = require_roles(*INVOICE_ROLES)


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/projects/{project_id}/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    project_id: UUID,
    user: dict = Depends(require_invoice_role),
    db: Client = Depends(get_supabase),
):
    """Invoices on a project (finance / executive / admin: all; others: their own)."""
    try:
        return await run_in_threadpool(svc.list_invoices, db, str(project_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post(
    "/projects/{project_id}/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_invoice(
    project_id: UUID,
    file: UploadFile = File(...),
    amount: str = Form(...),
    payee_name: str | None = Form(None),
    vendor_id: UUID | None = Form(None),
    invoice_number: str | None = Form(None),
    invoice_date: date | None = Form(None),
    notes: str | None = Form(None),
    user: dict = Depends(require_invoice_role),
    db: Client = Depends(get_supabase),
):
    """Upload an invoice for an internal T&M line (multipart)."""
    try:
        amount_value = Decimal(amount.strip().replace(",", "").replace("$", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Enter the invoice amount as a number.") from exc

    file_bytes = await read_upload(file, svc.FINANCE_BUCKET)
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    content_type = file.content_type or "application/octet-stream"
    filename = sanitize_filename(file.filename or "invoice")
    validate_upload(file_bytes, filename, content_type, svc.FINANCE_BUCKET)

    try:
        return await run_in_threadpool(
            lambda: svc.create_invoice(
                db,
                project_id=str(project_id),
                user=user,
                filename=filename,
                content_type=content_type,
                file_bytes=file_bytes,
                amount=amount_value,
                payee_name=payee_name,
                vendor_id=str(vendor_id) if vendor_id else None,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                notes=notes,
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.patch("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: UUID,
    payload: InvoiceUpdate,
    user: dict = Depends(require_invoice_role),
    db: Client = Depends(get_supabase),
):
    """Edit invoice details while it is not yet categorised."""
    try:
        return await run_in_threadpool(
            lambda: svc.update_invoice(db, invoice_id=str(invoice_id), payload=payload, user=user)
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/invoices/{invoice_id}/categorise", response_model=CategoriseResult)
async def categorise_invoice(
    invoice_id: UUID,
    payload: InvoiceCategorise,
    user: dict = Depends(require_invoice_role),
    db: Client = Depends(get_supabase),
):
    """Assign the invoice to an internal T&M line and start payment approval.
    An amount above the line's remaining allowance becomes a variance funded
    from contingency (baselined budgets)."""
    try:
        return await run_in_threadpool(
            lambda: svc.categorise_invoice(
                db, invoice_id=str(invoice_id), line_id=str(payload.budget_line_id), user=user
            )
        )
    except FinancialError as exc:
        raise _http(exc) from exc


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: UUID,
    user: dict = Depends(require_invoice_role),
    db: Client = Depends(get_supabase),
):
    """Cancel an invoice that is not yet in payment approval."""
    try:
        return await run_in_threadpool(lambda: svc.cancel_invoice(db, invoice_id=str(invoice_id), user=user))
    except FinancialError as exc:
        raise _http(exc) from exc


@router.get("/invoices/{invoice_id}/url", response_model=SignedUrlResponse)
async def invoice_url(
    invoice_id: UUID,
    user: dict = Depends(require_invoice_role),
    db: Client = Depends(get_supabase),
):
    """1-hour signed download URL for the invoice file."""
    try:
        url = await run_in_threadpool(lambda: svc.signed_url(db, invoice_id=str(invoice_id), user=user))
    except FinancialError as exc:
        raise _http(exc) from exc
    return SignedUrlResponse(url=url)
