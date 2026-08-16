"""
Contract envelope send orchestration (Task 9.3b, with 9.5 contract row + 9.4 email).

`send_contract_envelope(award_id)` is the single entry point used both as the
post-commit best-effort hook from `award_service.create_award` and as the manual
resend route. It:

  1. loads award → submission → invited contact, vendor, task, project
  2. creates the `contracts` row in `sent_for_signature` (9.5; re-entrant)
  3. returns early if an envelope already exists for the contract (idempotent resend)
  4. generates the contract PDF (+ signed SOW exhibit(s) when on file)
  5. builds + sends the two-signer envelope (BluOnX/owner routingOrder 1, vendor 2)
  6. persists the `docusign_envelopes` row (status `sent`)
  7. sends the award email (9.4)

All DocuSign SDK work is off the event loop (the client wraps it). The whole path
is offline under DOCUSIGN_PROVIDER=mock / EMAIL_PROVIDER=mock. Best-effort framing
(a send failure must not roll back the award) is the CALLER's responsibility — the
post-commit hook wraps this in try/except; the resend route surfaces failures.
"""

from __future__ import annotations

import base64
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.core.config import settings
from app.services import contract_service
from app.services.contract_pdf import (
    OWNER_SIGN_ANCHOR,
    VENDOR_SIGN_ANCHOR,
    build_contract_pdf,
)
from app.services.docusign_client import build_envelope_definition, get_docusign_client
from app.services.email_service import EmailService, create_email_provider
from app.services.pre_award_validation_service import _embed_one
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

_SOW_BUCKET = "project-documents"


class ContractEnvelopeError(Exception):
    """Raised on a hard send failure (used by the resend route)."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _first(data: Any) -> dict | None:
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _fmt_money(value: Any) -> str:
    if value in (None, ""):
        return "$0.00"
    try:
        return f"${Decimal(str(value)):,.2f}"
    except Exception:
        return str(value)


def _compute_end_date(start_date: Any, work_duration_days: Any) -> str | None:
    """Realize the task-scoped work end date as proposed_start + work_duration_days.
    Returns an ISO date string only when BOTH inputs are present;
    otherwise None — a null start or null duration leaves end_date unset and the
    PDF falls back to relative phrasing. Never raises on a null/blank/malformed
    start (the "Start Date SKIPPED" case). Fixes the prior bug where end_date was
    wrongly sourced from the whole project's estimated_end_date."""
    if start_date in (None, "") or not work_duration_days:
        return None
    if isinstance(start_date, datetime):
        base = start_date.date()
    elif isinstance(start_date, date):
        base = start_date
    else:
        try:
            base = date.fromisoformat(str(start_date)[:10])
        except ValueError:
            return None
    return (base + timedelta(days=int(work_duration_days))).isoformat()


def _date_only(value: Any) -> str | None:
    """Date part (YYYY-MM-DD) of a date/datetime/ISO string; None if blank."""
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def _fmt_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.strftime("%B %d, %Y")
    s = str(value)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%B %d, %Y")
    except ValueError:
        return s


def _load_award_context(award_id: str, *, db: Client) -> dict:
    """Resolve the award's full send context in one nested select. 404 → None."""
    resp = (
        db.table("awards")
        .select(
            "id, vendor_id, task_id, award_amount, bid_submission_id, status,"
            " instructions, contract_valid_days, work_duration_days, signer_id,"
            # Deliberately NOT !inner: signer_id is nullable, and awards created
            # before the signer roster existed must still load (they fall back to
            # the CONTRACT_OWNER_SIGNER_* settings). An inner join would drop them
            # from the result and surface as a spurious "Award not found".
            " contract_signers(full_name, email),"
            " bid_submissions!inner(proposed_start_date, sow_attested_at,"
            "   bid_invitations!inner(vendor_contacts!inner(full_name, email))),"
            " vendors!inner(company_name),"
            " tasks!inner(name, project_id,"
            "   projects!inner(name, estimated_end_date))"
        )
        .eq("id", str(award_id))
        .limit(1)
        .execute()
    )
    row = _first(resp.data)
    if row is None:
        raise ContractEnvelopeError(404, "Award not found")
    return row


# The last-resort owner identity, used when neither the roster nor config supplies
# one. Kept as literals (not config) so the send can never fail for want of a value.
_FALLBACK_SIGNER_NAME = "BluOnX Authorized Signer"
_FALLBACK_SIGNER_EMAIL = "owner@example.com"


def _candidate_signer(ctx: dict) -> tuple[str, str]:
    """Who BluOnX *would* put on a new contract for this award.

    Steps 2-4 of the resolution order: the award's chosen roster entry, then the
    CONTRACT_OWNER_SIGNER_* settings (which legacy awards with signer_id NULL
    still depend on), then the hardcoded fallback. Step 1 — an existing contract's
    snapshot — is applied by the caller, because it outranks all of these.
    """
    roster = _embed_one(ctx.get("contract_signers"))
    name = roster.get("full_name") or settings.CONTRACT_OWNER_SIGNER_NAME
    email = roster.get("email") or settings.CONTRACT_OWNER_SIGNER_EMAIL
    return (name or _FALLBACK_SIGNER_NAME, email or _FALLBACK_SIGNER_EMAIL)


def _resolve_owner_signer(ctx: dict, contract: dict) -> tuple[str, str]:
    """The BluOnX signer for THIS send, snapshot first.

    Once a contract carries `signer_name` / `signer_email`, that pair is the
    answer forever: `awards.signer_id` records which roster entry was chosen, it
    is not a live lookup after the first send. An admin correcting a signer's
    email must not change where an already-issued contract routes, nor what the
    contract record says about who signed it.

    A contract created before this feature has both columns NULL and falls
    through to the candidate, so those still send rather than routing nowhere.
    """
    name = contract.get("signer_name")
    email = contract.get("signer_email")
    if name and email:
        return (name, email)
    return _candidate_signer(ctx)


def _fetch_sow_exhibits(submission_id: str, *, db: Client) -> list[dict]:
    """Return the awarded package's Scope of Work as the single envelope exhibit.

    The SoW is the PM-uploaded `project_documents` row pinned on the package
    (`bid_packages.scope_of_work_document_id`), NOT a vendor bid_attachment.
    Resolve it via the awarded submission → bid_invitation → bid_package, then
    download from the project-documents bucket and attach as document 2 (the
    contract PDF is document 1). No SignHere tab is placed on the exhibit — only
    the contract PDF carries the signing anchors.

    Best-effort: a missing SoW or storage error drops the exhibit rather than
    failing the whole send (the signed-SoW DATE still rides on the contract PDF).

    Two explicit lookups (submission chain → SoW id, then the doc by id) rather
    than a nested PostgREST embed: bid_packages has both a direct FK to
    project_documents AND a many-to-many via bid_package_documents, so an
    embedded select would be ambiguous."""
    try:
        chain = (
            db.table("bid_submissions")
            .select("bid_invitations!inner(bid_packages!inner(scope_of_work_document_id))")
            .eq("id", str(submission_id))
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("Failed to resolve SOW document for submission %s", submission_id)
        return []

    row = _first(chain.data)
    invitation = _embed_one((row or {}).get("bid_invitations"))
    package = _embed_one(invitation.get("bid_packages"))
    sow_doc_id = package.get("scope_of_work_document_id")
    if not sow_doc_id:
        logger.warning("No SOW document on package for submission %s", submission_id)
        return []

    try:
        doc_resp = (
            db.table("project_documents")
            .select("file_name, file_path")
            .eq("id", str(sow_doc_id))
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("Failed to load SOW document %s", sow_doc_id)
        return []

    sow_doc = _first(doc_resp.data) or {}
    path = sow_doc.get("file_path")
    if not path:
        logger.warning("SOW document %s has no file_path", sow_doc_id)
        return []

    try:
        raw = db.storage.from_(_SOW_BUCKET).download(path)
    except Exception:
        logger.exception("Failed to download SOW exhibit %s", path)
        return []

    file_name = sow_doc.get("file_name") or "scope-of-work.pdf"
    return [
        {
            "document_base64": base64.b64encode(raw).decode("ascii"),
            "name": file_name,
            "document_id": "2",  # contract PDF is document 1
            "file_extension": file_name.split(".")[-1],
        }
    ]


async def send_contract_envelope(
    award_id: str,
    *,
    db: Client,
    client=None,
    email_service: EmailService | None = None,
) -> dict:
    """Create the contract, send the envelope, persist it, and email the vendor.
    Returns the `docusign_envelopes` row. Re-entrant: an already-sent envelope is
    returned as-is (no double send).

    supabase-py is synchronous; every DB / Storage call here is offloaded to the
    threadpool so this awaited path (post-commit hook + resend route) never blocks
    the event loop. The PDF build and the DocuSign send are already off-loop."""
    ctx = await run_in_threadpool(lambda: _load_award_context(award_id, db=db))

    submission = _embed_one(ctx.get("bid_submissions"))
    invitation = _embed_one(submission.get("bid_invitations"))
    contact = _embed_one(invitation.get("vendor_contacts"))
    vendor = _embed_one(ctx.get("vendors"))
    task = _embed_one(ctx.get("tasks"))
    project = _embed_one(task.get("projects"))

    start_date = submission.get("proposed_start_date")
    # Task-scoped end date: proposed_start + work_duration_days. NULL
    # when either is missing — no longer the whole project's estimated_end_date.
    end_date = _compute_end_date(start_date, ctx.get("work_duration_days"))

    # Signed-SoW date = the awarded submission's attestation timestamp (date part).
    # Every post-feature submission is stamped at submit, so a NULL here means an
    # award on a pre-feature/never-attested submission — fail loud rather than
    # silently send a contract with no signed-SoW date.
    sow_attested_at = submission.get("sow_attested_at")
    if sow_attested_at in (None, ""):
        raise ContractEnvelopeError(
            422,
            "Awarded submission has no Scope of Work attestation timestamp; "
            "cannot send a contract without a signed-SoW date.",
        )
    sow_signed_date = _date_only(sow_attested_at)

    # 2) Contract row (re-entrant) — born in sent_for_signature so the FK holds.
    #    The candidate signer is frozen onto it in this same write; if the row
    #    already exists it comes back untouched, snapshot and all.
    candidate_name, candidate_email = _candidate_signer(ctx)
    contract = await run_in_threadpool(
        lambda: contract_service.create_contract_for_award(
            ctx,
            start_date=start_date,
            end_date=end_date,
            sow_signed_date=sow_signed_date,
            signer_name=candidate_name,
            signer_email=candidate_email,
            db=db,
        )
    )
    contract_id = contract["id"]

    # The contract is now authoritative for who signs: a fresh row carries the
    # candidate we just wrote, an existing one carries whatever it was issued with.
    owner_signer_name, owner_signer_email = _resolve_owner_signer(ctx, contract)

    # 3) Idempotent resend — reuse an existing envelope for this contract.
    existing = await run_in_threadpool(
        lambda: db.table("docusign_envelopes")
        .select("*")
        .eq("contract_id", str(contract_id))
        .limit(1)
        .execute()
    )
    existing_env = _first(existing.data)
    if existing_env:
        return existing_env

    # 4) Contract PDF (+ SOW exhibits if present).
    pdf_context = {
        "contract_number": contract.get("contract_number"),
        "vendor_company": vendor.get("company_name"),
        "vendor_contact_name": contact.get("full_name"),
        # Same resolved identity as the routingOrder-1 recipient below: the name
        # printed on the contract and the person DocuSign routes to are one
        # decision, made once.
        "owner_signer_name": owner_signer_name,
        "award_amount": ctx.get("award_amount"),
        "start_date": start_date,
        "end_date": end_date,
        "project_name": project.get("name"),
        "task_name": task.get("name"),
        "payment_terms": contract.get("payment_terms"),
        # Contract-term rendering. Validity is relative at send-time
        # (the concrete valid_until is unknown until signing); work duration drives
        # the schedule clause. sow_signed_date = awarded submission's attestation date.
        "contract_valid_days": ctx.get("contract_valid_days"),
        "work_duration_days": ctx.get("work_duration_days"),
        "sow_signed_date": sow_signed_date,
        # Firm contact-information block, from config (values supplied via env).
        "firm_name": settings.CONTRACT_FIRM_NAME,
        "firm_contact_email": settings.CONTRACT_FIRM_CONTACT_EMAIL,
        "firm_contact_phone": settings.CONTRACT_FIRM_CONTACT_PHONE,
        "firm_contact_address": settings.CONTRACT_FIRM_CONTACT_ADDRESS,
    }
    pdf_bytes = await run_in_threadpool(build_contract_pdf, pdf_context)
    documents = [
        {
            "document_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "name": f"Subcontract {contract.get('contract_number', '')}".strip(),
            "document_id": "1",
            "file_extension": "pdf",
        }
    ]
    documents.extend(
        await run_in_threadpool(
            lambda: _fetch_sow_exhibits(ctx.get("bid_submission_id"), db=db)
        )
    )

    # 5) Two sequential signers — BluOnX signs first (routingOrder 1), then the
    #    vendor countersigns (routingOrder 2). Sequential routing means the vendor
    #    only receives the DocuSign request once BluOnX has signed. recipient_id
    #    tracks the signing order; the anchor tab stays bound to the correct party.
    signers = [
        {
            "name": owner_signer_name,
            "email": owner_signer_email,
            "recipient_id": "1",
            "routing_order": "1",
            "anchor_string": OWNER_SIGN_ANCHOR,
        },
        {
            "name": contact.get("full_name") or vendor.get("company_name") or "Subcontractor",
            "email": contact.get("email"),
            "recipient_id": "2",
            "routing_order": "2",
            "anchor_string": VENDOR_SIGN_ANCHOR,
        },
    ]
    definition = build_envelope_definition(
        documents=documents,
        signers=signers,
        webhook_url=settings.DOCUSIGN_CONNECT_WEBHOOK_URL,
        email_subject=(
            f"Please sign your BluOnX subcontract for {project.get('name', '')}"
        ).strip(),
    )

    ds_client = client or get_docusign_client()
    envelope_id = await ds_client.send_envelope(definition)

    # 6) Persist the envelope row (contract stays sent_for_signature).
    env_resp = await run_in_threadpool(
        lambda: db.table("docusign_envelopes")
        .insert(
            {
                "contract_id": str(contract_id),
                "envelope_id": envelope_id,
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .execute()
    )
    envelope_row = _first(env_resp.data) or {
        "contract_id": str(contract_id),
        "envelope_id": envelope_id,
        "status": "sent",
    }

    # 7) Award email (9.4) — best-effort; a mail failure must not undo the send.
    try:
        await _send_award_email(
            contact=contact,
            vendor=vendor,
            project=project,
            task=task,
            contract=contract,
            award=ctx,
            start_date=start_date,
            db=db,
            email_service=email_service,
        )
    except Exception:
        logger.exception("Award email failed for award %s (envelope already sent)", award_id)

    return envelope_row


async def _send_award_email(
    *,
    contact: dict,
    vendor: dict,
    project: dict,
    task: dict,
    contract: dict,
    award: dict,
    start_date: Any,
    db: Client,
    email_service: EmailService | None,
) -> None:
    to_email = contact.get("email")
    if not to_email:
        logger.warning("No vendor contact email on award %s; skipping award email", award.get("id"))
        return
    context = {
        "vendor_contact_name": contact.get("full_name") or "Vendor",
        "vendor_company": vendor.get("company_name") or "your company",
        "project_name": project.get("name") or "the project",
        "task_name": task.get("name") or "the contracted scope",
        "award_amount_formatted": _fmt_money(award.get("award_amount")),
        "contract_number": contract.get("contract_number"),
        "start_date_formatted": _fmt_date(start_date),
        # PM-authored guidance, stored on the award; reused as-is on resend since
        # this context is reloaded from the awards row each time.
        "instructions": award.get("instructions"),
    }
    html_body = template_renderer.render("award_notification.html", context)
    plain_text_body = template_renderer.render_text("award_notification.txt", context)
    service = email_service or EmailService(provider=create_email_provider(), db_client=db)
    await service.send_email(
        to_email=to_email,
        subject=f"You've been awarded: {context['project_name']} ({context['task_name']})",
        html_body=html_body,
        plain_text_body=plain_text_body,
        email_type="award_notification",
        recipient_type="vendor_contact",
        reference_type="awards",
        reference_id=str(award.get("id")),
    )
