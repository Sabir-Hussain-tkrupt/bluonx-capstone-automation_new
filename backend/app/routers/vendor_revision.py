"""Vendor revision decline — /api/v1/vendor-portal/revision-requests/{id}/decline

A GET click-through from the emailed link (browser navigation, no Bearer
JWT possible). The raw magic-link token in the query string is the
credential, validated server-side like vendor_auth does. Returns a
server-rendered styled HTML page (success or error), never raw JSON.

This is a separate router from vendor_portal.py (which is JWT-gated) so the
vendor-portal boundary stays explicit — this endpoint deliberately does NOT
use get_vendor_context.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from supabase import Client

from app.core.supabase_client import get_supabase
from app.services.bid_revision_service import (
    BidRevisionValidationError,
    decline_revision_request_via_token,
)
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vendor-portal")


@router.get(
    "/revision-requests/{revision_request_id}/decline",
    response_class=HTMLResponse,
)
async def decline_revision_request_endpoint(
    revision_request_id: UUID,
    token: str,
    db: Client = Depends(get_supabase),
) -> HTMLResponse:
    """Vendor declines a revision request via the emailed link."""
    try:
        decline_revision_request_via_token(
            db,
            revision_request_id=revision_request_id,
            raw_token=token,
        )
    except BidRevisionValidationError as exc:
        html = template_renderer.render(
            "revision_link_error.html", {"message": exc.detail}
        )
        return HTMLResponse(content=html, status_code=exc.status_code)

    html = template_renderer.render("revision_decline_confirmation.html", {})
    return HTMLResponse(content=html, status_code=200)
