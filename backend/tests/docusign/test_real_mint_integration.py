"""Real sandbox JWT mint — manual/CI-skipped integration test (Task 9.3a).

Skipped unless DOCUSIGN_PROVIDER=sandbox and the credentials are present, and
requires that one-time consent has already been granted for the impersonated
user. Mirrors the test-discipline convention of test_ses_integration.py.
"""

from __future__ import annotations

import os

import pytest

from app.core.config import settings
from app.services.docusign_client import (
    DocuSignClient,
    SandboxDocuSignAuthProvider,
)

_CREDS_PRESENT = bool(
    settings.DOCUSIGN_PROVIDER == "sandbox"
    and settings.DOCUSIGN_INTEGRATION_KEY
    and settings.DOCUSIGN_USER_ID
    and settings.DOCUSIGN_PRIVATE_KEY_PATH
    and os.path.exists(settings.DOCUSIGN_PRIVATE_KEY_PATH or "")
)

pytestmark = pytest.mark.skipif(
    not _CREDS_PRESENT,
    reason="DocuSign sandbox creds not configured (DOCUSIGN_PROVIDER!=sandbox or key missing)",
)


@pytest.mark.asyncio
async def test_real_sandbox_mint_returns_token():
    client = DocuSignClient(provider=SandboxDocuSignAuthProvider())
    token = await client.get_access_token()
    assert isinstance(token, str) and len(token) > 0
