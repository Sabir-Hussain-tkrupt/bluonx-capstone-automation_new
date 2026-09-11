"""DocuSign health endpoint — GET /api/v1/admin/docusign-health

Diagnostic that attempts a JWT token mint and reports the result. On the first
run (before the impersonated user has granted consent) it surfaces the one-time
consent URL so the grant is self-service. Internal-auth only — mirrors the
/admin/scheduler-health convention.
"""

import logging

from fastapi import APIRouter, Depends

from app.core.auth import require_admin
from app.core.config import settings
from app.services.docusign_client import (
    DocuSignClient,
    DocuSignConsentRequired,
    get_docusign_client,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/admin/docusign-health")
async def docusign_health(
    user: dict = Depends(require_admin),
    client: DocuSignClient = Depends(get_docusign_client),
) -> dict:
    """Mint a token and report ok, or surface the one-time consent URL."""
    try:
        await client.get_access_token()
    except DocuSignConsentRequired as exc:
        return {
            "ok": False,
            "provider": settings.DOCUSIGN_PROVIDER,
            "consent_required": True,
            "consent_url": exc.consent_url,
        }
    except Exception as exc:
        logger.error("DocuSign health check failed: %s", exc)
        return {
            "ok": False,
            "provider": settings.DOCUSIGN_PROVIDER,
            "error": str(exc),
        }
    return {"ok": True, "provider": settings.DOCUSIGN_PROVIDER}
