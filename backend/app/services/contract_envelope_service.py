"""
Contract envelope send orchestration (Task 9.3b, with 9.5 contract row + 9.4 email).

`send_contract_envelope(award_id)` is the single entry point used both as the
post-commit best-effort hook from `award_service.create_award` and as the manual
resend route. It:

  1. loads award → submission → invited contact, vendor, task, project
  2. creates the `contracts` row in `sent_for_signature` (9.5; re-entrant)
  3. returns early if an envelope already exists for the contract (idempotent resend)
  4. generates the contract PDF (+ signed SOW exhibit(s) when on file)
  5. builds + sends the two-signer envelope (vendor routingOrder 1, owner 2)
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
from datetime import date, datetime, timezone
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

_SOW_BUCKET = "bid-attachments"


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
            " instructions,"
            " bid_submissions!inner(proposed_start_date,"
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


def _fetch_sow_exhibits(submission_id: str, *, db: Client) -> list[dict]:
    """Download the awarded submission's attachments (signed SOW lives here) from
    Storage and return them as envelope documents. Best-effort — a storage error
    drops the exhibit rather than failing the whole send.

    NOTE: `bid_attachments` has no SOW-type discriminator, so we exhibit ALL of the
    submission's attachments (flagged in DEFERRED — a type field would refine this)."""
    try:
        resp = (
            db.table("bid_attachments")
            .select("file_name, file_path")
            .eq("bid_submission_id", str(submission_id))
            .execute()
        )
    except Exception:
        logger.exception("Failed to list SOW attachments for submission %s", submission_id)
        return []

    exhibits: list[dict] = []
    storage = db.storage.from_(_SOW_BUCKET)
    for i, att in enumerate(resp.data or []):
        path = att.get("file_path")
        if not path:
            continue
        try:
            raw = storage.download(path)
        except Exception:
            logger.exception("Failed to download SOW exhibit %s", path)
            continue
        exhibits.append(
            {
                "document_base64": base64.b64encode(raw).decode("ascii"),
                "name": att.get("file_name") or f"Exhibit {i + 1}",
                "document_id": str(i + 2),  # contract PDF is document 1
                "file_extension": (att.get("file_name") or "exhibit.pdf").split(".")[-1],
            }
        )
    return exhibits


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
    end_date = project.get("estimated_end_date")

    # 2) Contract row (re-entrant) — born in sent_for_signature so the FK holds.
    contract = await run_in_threadpool(
        lambda: contract_service.create_contract_for_award(
            ctx, start_date=start_date, end_date=end_date, db=db
        )
    )
    contract_id = contract["id"]

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
        "owner_signer_name": settings.CONTRACT_OWNER_SIGNER_NAME,
        "award_amount": ctx.get("award_amount"),
        "start_date": start_date,
        "end_date": end_date,
        "project_name": project.get("name"),
        "task_name": task.get("name"),
        "payment_terms": contract.get("payment_terms"),
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

    # 5) Two sequential signers — vendor (1) then internal countersigner (2).
    signers = [
        {
            "name": contact.get("full_name") or vendor.get("company_name") or "Subcontractor",
            "email": contact.get("email"),
            "recipient_id": "1",
            "routing_order": "1",
            "anchor_string": VENDOR_SIGN_ANCHOR,
        },
        {
            "name": settings.CONTRACT_OWNER_SIGNER_NAME or "BluOnX Authorized Signer",
            "email": settings.CONTRACT_OWNER_SIGNER_EMAIL or "owner@example.com",
            "recipient_id": "2",
            "routing_order": "2",
            "anchor_string": OWNER_SIGN_ANCHOR,
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
