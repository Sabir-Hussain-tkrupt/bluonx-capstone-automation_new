"""
DocuSign Connect status webhook (Task 9.3b, Part B) — the acceptance hub.

Kept DELIBERATELY SEPARATE from the SES/SNS `webhooks.py`. Connect callbacks drive
the contract-acceptance lifecycle:

  completed         → contract `executed`, award `accepted` (+1 capacity via the DB
                      trigger), declines dispatched to the other invited vendors
  declined / voided → contract `terminated`, award `declined_by_vendor`
  delivered / sent  → status update only

Security + correctness invariants:
  • HMAC-verify the RAW request body before parsing (SHA-256, base64, constant-time
    compare against X-DocuSign-Signature-1). Reject mismatches with 401.
  • Idempotent across Connect's retries (up to 5× / 72h): if the stored envelope is
    already at the incoming terminal status, the whole handler no-ops — so a duplicate
    `completed` never double-executes the contract, double-bumps capacity, or
    double-sends declines.
  • Every event updates `docusign_envelopes.status` and stores the full
    `webhook_payload` (JSONB) for audit/debug.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.services import contract_service, decline_service
from app.services.pre_award_validation_service import _embed_one

logger = logging.getLogger(__name__)

router = APIRouter()

_SIGNATURE_HEADER = "X-DocuSign-Signature-1"
_TERMINAL = ("completed", "declined", "voided")
# event string → normalized envelope status (fallback when envelopeSummary absent).
_EVENT_TO_STATUS = {
    "envelope-sent": "sent",
    "envelope-delivered": "delivered",
    "envelope-completed": "completed",
    "envelope-declined": "declined",
    "envelope-voided": "voided",
}


# ── HMAC verification (pure) ──────────────────────────────────────────────────


def verify_connect_hmac(raw_body: bytes, signature_header: str | None) -> bool:
    """Constant-time-verify the raw body against the configured Connect HMAC key.

    Fail-closed: a missing key or missing signature header → reject."""
    key = settings.DOCUSIGN_CONNECT_HMAC_KEY
    if not key or not signature_header:
        return False
    computed = base64.b64encode(
        hmac.new(key.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(computed, signature_header)


# ── Payload extraction ────────────────────────────────────────────────────────


def extract_event(payload: dict) -> tuple[str | None, str | None]:
    """Pull (envelope_id, normalized_status) from a Connect JSON SIM payload.

    Handles the modern shape `{event, data:{envelopeId, envelopeSummary:{status}}}`
    and falls back to the event string / top-level envelopeId."""
    data = payload.get("data") or {}
    envelope_id = (
        data.get("envelopeId")
        or payload.get("envelopeId")
        or payload.get("EnvelopeID")
    )
    summary = data.get("envelopeSummary") or {}
    raw_status = summary.get("status") or payload.get("status")
    if not raw_status:
        raw_status = _EVENT_TO_STATUS.get(str(payload.get("event", "")).lower())
    return (
        str(envelope_id) if envelope_id else None,
        str(raw_status).lower() if raw_status else None,
    )


def _first(data: Any) -> dict | None:
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


# ── Dispatch ──────────────────────────────────────────────────────────────────


async def handle_envelope_event(
    *,
    envelope_id: str,
    status: str | None,
    payload: dict,
    db,
    email_service=None,
) -> str:
    """Apply one Connect event. Returns "noop" | "applied" | "unknown".

    The single idempotency guard (stored terminal status == incoming) protects every
    downstream side effect, so retries are safe."""
    resp = (
        db.table("docusign_envelopes")
        .select(
            "id, status, contract_id,"
            " contracts!inner(id, status, award_id,"
            "   awards!inner(id, status, vendor_id, task_id, bid_submission_id,"
            "     contract_valid_days,"
            "     bid_submissions!inner(bid_invitations!inner(bid_package_id))))"
        )
        .eq("envelope_id", str(envelope_id))
        .limit(1)
        .execute()
    )
    env = _first(resp.data)
    if env is None:
        logger.info("Connect event for unknown envelope %s — ignoring", envelope_id)
        return "unknown"

    stored_status = env.get("status")
    if status in _TERMINAL and stored_status == status:
        # Already applied — duplicate retry. No-op (no double execute / capacity / declines).
        return "noop"

    # Always: persist the new status + full payload (audit trail).
    update: dict[str, Any] = {"status": status, "webhook_payload": payload}
    if status == "completed":
        update["completed_at"] = datetime.now(timezone.utc).isoformat()
    db.table("docusign_envelopes").update(update).eq("id", env["id"]).execute()

    contract = _embed_one(env.get("contracts"))
    contract_id = contract.get("id") or env.get("contract_id")
    award = _embed_one(contract.get("awards"))

    if status == "completed":
        contract_service.mark_contract_executed(
            contract_id, contract_valid_days=award.get("contract_valid_days"), db=db
        )
        if award.get("status") != "accepted":
            db.table("awards").update({"status": "accepted"}).eq(
                "id", award["id"]
            ).execute()
        # Close the package on acceptance (evaluating -> closed). Guarded on the
        # current status so it's idempotent across Connect retries and only fires
        # the evaluating -> closed transition.
        submission = _embed_one(award.get("bid_submissions"))
        invitation = _embed_one(submission.get("bid_invitations"))
        bid_package_id = invitation.get("bid_package_id")
        if bid_package_id:
            db.table("bid_packages").update({"status": "closed"}).eq(
                "id", str(bid_package_id)
            ).eq("status", "evaluating").execute()
            # Declines to the backup pool (9.6), fired only now (winner has signed).
            await decline_service.send_decline_notifications(
                bid_package_id=bid_package_id,
                winning_vendor_id=award.get("vendor_id"),
                db=db,
                email_service=email_service,
            )
        return "applied"

    if status in ("declined", "voided"):
        contract_service.mark_contract_terminated(contract_id, db=db)
        if award.get("status") != "declined_by_vendor":
            db.table("awards").update({"status": "declined_by_vendor"}).eq(
                "id", award["id"]
            ).execute()
        return "applied"

    # delivered / sent → status update only (already persisted above).
    return "applied"


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/webhooks/docusign-connect")
async def docusign_connect(request: Request) -> Response:
    """Receive DocuSign Connect envelope status callbacks.

    Public endpoint (no JWT) — the HMAC over the raw body is the gate. Returns 401 on
    a bad/missing signature, 200 once the event is processed (or harmlessly ignored)."""
    raw = await request.body()
    signature = request.headers.get(_SIGNATURE_HEADER)
    if not verify_connect_hmac(raw, signature):
        logger.warning("DocuSign Connect: invalid HMAC signature; rejecting")
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, content="Invalid signature")

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("DocuSign Connect: body is not valid JSON")
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid payload")

    envelope_id, env_status = extract_event(payload)
    if not envelope_id:
        logger.info("DocuSign Connect: no envelopeId in payload; ignoring")
        return Response(status_code=200, content="OK")

    db = get_supabase(request)
    await handle_envelope_event(
        envelope_id=envelope_id, status=env_status, payload=payload, db=db
    )
    return Response(status_code=200, content="OK")
