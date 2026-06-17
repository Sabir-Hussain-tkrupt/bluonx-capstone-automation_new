"""
Live sandbox envelope round-trip — SKIPPED unless real DocuSign creds are present.

Mirrors test_real_mint_integration.py (9.3a). Requires DOCUSIGN_PROVIDER=sandbox,
the three creds + the .pem on disk, AND one-time consent already granted, AND a
real award/contract context in the DB. This is an opt-in manual integration test,
never part of the offline unit run.
"""

import os

import pytest

from app.core.config import settings

_PRIVATE_KEY_PRESENT = bool(
    settings.DOCUSIGN_PRIVATE_KEY_PATH
    and os.path.exists(settings.DOCUSIGN_PRIVATE_KEY_PATH)
)
_CREDS_PRESENT = (
    settings.DOCUSIGN_PROVIDER == "sandbox"
    and bool(settings.DOCUSIGN_INTEGRATION_KEY)
    and bool(settings.DOCUSIGN_USER_ID)
    and bool(settings.DOCUSIGN_ACCOUNT_ID)
    and _PRIVATE_KEY_PRESENT
)

_REQUIRES = "Requires DOCUSIGN_PROVIDER=sandbox + creds + consent + a live award id"


@pytest.mark.skipif(not _CREDS_PRESENT, reason=_REQUIRES)
async def test_live_envelope_round_trip():
    """Send a real sandbox envelope for AWARD_ID_FOR_INTEGRATION and assert an
    envelope id comes back. Set the env var to a real award id to run."""
    award_id = os.getenv("AWARD_ID_FOR_INTEGRATION")
    if not award_id:
        pytest.skip("Set AWARD_ID_FOR_INTEGRATION to a real award id to run")

    from app.core.supabase_client import init_supabase
    from app.services.contract_envelope_service import send_contract_envelope

    db = init_supabase(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    envelope = await send_contract_envelope(award_id, db=db)
    assert envelope.get("envelope_id")
