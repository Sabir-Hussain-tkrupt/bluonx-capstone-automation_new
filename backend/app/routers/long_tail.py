"""Long-tail items (Phase 7) — /api/v1/projects/{id}/long-tail, /escrows, /property-taxes, /jurisdictions

  * read ......................................... any active user
  * set up / edit escrows, post, release, cancel .. project manager or admin
  * works built, inspection, defects, sign-off .... field manager, project manager or admin
  * property taxes, bond renewals .................. project manager, finance or admin
  * cities / counties ............................. project manager, finance or admin
  (every rule is re-checked in SQL)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.core.auth import get_current_active_user, require_roles
from app.core.file_validation import read_upload, sanitize_filename, validate_upload
from app.core.supabase_client import get_supabase
from app.models.long_tail import (
    BondRenewal,
    DefectSave,
    EscrowSave,
    EscrowTransition,
    JurisdictionSave,
    SoldPortion,
    TaxUpdate,
    TaxYearSave,
)
from app.services import financial_health_service, long_tail_service as svc
from app.services.email_service import EmailService, get_email_service
from app.services.financial_errors import FinancialError

router = APIRouter()
_tax_roles = require_roles("project_manager", "finance")


def _http(exc: FinancialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _changed(db: Client, project_id, email_service: EmailService) -> None:
    """Long-tail lines move contingency: re-check the guardrails."""
    await financial_health_service.after_change(db, project_id, email_service)


# ── View ────────────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/long-tail")
async def get_long_tail(project_id: UUID, user: dict = Depends(get_current_active_user), db: Client = Depends(get_supabase)):
    """Open escrows with their two costs, upcoming taxes, reserve vs contingency."""
    try:
        return await run_in_threadpool(svc.overview, db, str(project_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Jurisdictions ───────────────────────────────────────────────────────────


@router.get("/jurisdictions")
async def list_jurisdictions(user: dict = Depends(get_current_active_user), db: Client = Depends(get_supabase)):
    return await run_in_threadpool(svc.list_jurisdictions, db)


@router.post("/jurisdictions", status_code=201)
async def create_jurisdiction(payload: JurisdictionSave, user: dict = Depends(_tax_roles), db: Client = Depends(get_supabase)):
    try:
        return await run_in_threadpool(
            lambda: svc.save_jurisdiction(db, jurisdiction_id=None, payload=payload, actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc


@router.put("/jurisdictions/{jurisdiction_id}")
async def update_jurisdiction(
    jurisdiction_id: UUID, payload: JurisdictionSave, user: dict = Depends(_tax_roles), db: Client = Depends(get_supabase),
):
    try:
        return await run_in_threadpool(
            lambda: svc.save_jurisdiction(db, jurisdiction_id=str(jurisdiction_id), payload=payload,
                                          actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Escrows ─────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/escrows", status_code=201)
async def create_escrow(
    project_id: UUID, payload: EscrowSave, user: dict = Depends(require_roles("project_manager")),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    """Creates the escrow and its two budget lines (premium, repairs)."""
    try:
        row = await run_in_threadpool(lambda: svc.save_escrow(
            db, project_id=str(project_id), escrow_id=None, payload=payload, actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, project_id, email_service)
    return row


@router.get("/escrows/{escrow_id}")
async def get_escrow(escrow_id: UUID, user: dict = Depends(get_current_active_user), db: Client = Depends(get_supabase)):
    try:
        return await run_in_threadpool(svc.escrow_detail, db, str(escrow_id), user)
    except FinancialError as exc:
        raise _http(exc) from exc


@router.put("/escrows/{escrow_id}")
async def update_escrow(
    escrow_id: UUID, payload: EscrowSave, user: dict = Depends(require_roles("project_manager")),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    try:
        current = await run_in_threadpool(svc.get_escrow, db, str(escrow_id))
        row = await run_in_threadpool(lambda: svc.save_escrow(
            db, project_id=str(current["project_id"]), escrow_id=str(escrow_id), payload=payload,
            actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, row["project_id"], email_service)
    return row


@router.post("/escrows/{escrow_id}/transition")
async def escrow_transition(
    escrow_id: UUID, payload: EscrowTransition, user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    """posted → works built → inspection → corrections → signed off → released."""
    try:
        row = await run_in_threadpool(lambda: svc.transition(
            db, escrow_id=str(escrow_id), to=payload.to, on=payload.on, note=payload.note,
            signoff_by=payload.signoff_by, actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, row["project_id"], email_service)
    return row


@router.post("/escrows/{escrow_id}/defects", status_code=201)
async def add_defect(
    escrow_id: UUID, payload: DefectSave, user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    try:
        row = await run_in_threadpool(lambda: svc.save_defect(
            db, escrow_id=str(escrow_id), defect_id=None, payload=payload, actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, row["project_id"], email_service)
    return row


@router.put("/escrows/{escrow_id}/defects/{defect_id}")
async def update_defect(
    escrow_id: UUID, defect_id: UUID, payload: DefectSave, user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    try:
        row = await run_in_threadpool(lambda: svc.save_defect(
            db, escrow_id=str(escrow_id), defect_id=str(defect_id), payload=payload, actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, row["project_id"], email_service)
    return row


@router.post("/escrows/{escrow_id}/renew")
async def renew_bond(
    escrow_id: UUID, payload: BondRenewal, user: dict = Depends(_tax_roles),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    """New expiry date; the renewal premium is added to the premium line."""
    try:
        row = await run_in_threadpool(lambda: svc.renew_bond(
            db, escrow_id=str(escrow_id), new_expiry=payload.new_expiry_date, premium=payload.premium,
            actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, row["project_id"], email_service)
    return row


@router.post("/escrows/{escrow_id}/document")
async def upload_escrow_document(
    escrow_id: UUID, file: UploadFile = File(...), user: dict = Depends(require_roles("project_manager", "finance")),
    db: Client = Depends(get_supabase),
):
    """Bond / escrow document into the finance-documents bucket."""
    data = await read_upload(file, svc.FINANCE_BUCKET)
    filename = sanitize_filename(file.filename or "bond.pdf")
    content_type = file.content_type or "application/octet-stream"
    validate_upload(data, filename, content_type, svc.FINANCE_BUCKET)
    try:
        return await run_in_threadpool(lambda: svc.upload_document(
            db, escrow_id=str(escrow_id), filename=filename, content_type=content_type, data=data))
    except FinancialError as exc:
        raise _http(exc) from exc


@router.get("/escrows/{escrow_id}/document")
async def escrow_document(escrow_id: UUID, user: dict = Depends(get_current_active_user), db: Client = Depends(get_supabase)):
    try:
        return {"url": await run_in_threadpool(svc.document_url, db, str(escrow_id))}
    except FinancialError as exc:
        raise _http(exc) from exc


# ── Property taxes ──────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/property-taxes", status_code=201)
async def set_tax_year(
    project_id: UUID, payload: TaxYearSave, user: dict = Depends(_tax_roles),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    """One tax year: a budget line and the city / county's instalments."""
    try:
        out = await run_in_threadpool(lambda: svc.set_tax_year(
            db, project_id=str(project_id), payload=payload, actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, project_id, email_service)
    return out


@router.patch("/property-taxes/{tax_id}")
async def update_tax(
    tax_id: UUID, payload: TaxUpdate, user: dict = Depends(_tax_roles),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    """Billed / actual amount, due date, paid, cancelled."""
    try:
        out = await run_in_threadpool(lambda: svc.update_tax(db, tax_id=str(tax_id), payload=payload,
                                                             actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, out["project_id"], email_service)
    return out


@router.post("/projects/{project_id}/property-taxes/sold-portion")
async def set_sold_portion(
    project_id: UUID, payload: SoldPortion, user: dict = Depends(_tax_roles),
    db: Client = Depends(get_supabase), email_service: EmailService = Depends(get_email_service),
):
    """Share of the land sold: open instalments from that year on are reduced."""
    try:
        n = await run_in_threadpool(lambda: svc.set_sold_portion(
            db, project_id=str(project_id), percent=payload.percent, from_year=payload.from_year,
            actor_id=user["user_id"]))
    except FinancialError as exc:
        raise _http(exc) from exc
    await _changed(db, project_id, email_service)
    return {"updated": n}
