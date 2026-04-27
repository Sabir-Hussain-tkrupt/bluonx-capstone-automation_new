"""
Tests for the get_vendor_context FastAPI dependency.

A throwaway endpoint (`/api/v1/__vendor_auth_test__/protected`) is registered
in conftest.py and protected by the dependency. Each test forges a token and
inspects the protected endpoint's response.

Critical case: the secret-isolation guard. A token signed with
SUPABASE_JWT_SECRET (the admin secret) MUST NOT satisfy the vendor middleware,
even if the type claim were spoofed — because the type guard fires first.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from app.core.config import settings
from app.core.vendor_auth import (
    VENDOR_JWT_ALGORITHM,
    VENDOR_TOKEN_TYPE,
    VendorContext,
    issue_vendor_jwt,
)

PROTECTED_PATH = "/api/v1/__vendor_auth_test__/protected"


def _ctx() -> VendorContext:
    return VendorContext(
        vendor_id=uuid4(),
        vendor_contact_id=uuid4(),
        bid_invitation_id=uuid4(),
        bid_package_id=uuid4(),
        task_id=uuid4(),
    )


async def test_valid_vendor_jwt_returns_context_matching_claims(vendor_client):
    ctx = _ctx()
    token = issue_vendor_jwt(ctx)
    resp = await vendor_client.get(
        PROTECTED_PATH, headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["vendor_id"] == str(ctx.vendor_id)
    assert body["vendor_contact_id"] == str(ctx.vendor_contact_id)
    assert body["bid_invitation_id"] == str(ctx.bid_invitation_id)
    assert body["bid_package_id"] == str(ctx.bid_package_id)
    assert body["task_id"] == str(ctx.task_id)


async def test_missing_authorization_header_returns_401(vendor_client):
    resp = await vendor_client.get(PROTECTED_PATH)
    # FastAPI HTTPBearer with auto_error=True returns 403 for missing creds,
    # 401 for malformed scheme. Both are acceptable "no access" responses,
    # but production code consistently uses HTTPBearer's defaults.
    assert resp.status_code in (401, 403)


async def test_malformed_bearer_value_returns_401(vendor_client):
    resp = await vendor_client.get(
        PROTECTED_PATH, headers={"Authorization": "Bearer not.a.real.jwt"}
    )
    assert resp.status_code == 401


async def test_token_signed_with_supabase_secret_is_rejected(vendor_client):
    """The secret-isolation guard: admin tokens must never satisfy vendor auth."""
    forged = jwt.encode(
        {
            "type": VENDOR_TOKEN_TYPE,  # even with the right type claim,
            "vendor_id": str(uuid4()),  # the signature won't verify against
            "vendor_contact_id": str(uuid4()),  # the vendor secret.
            "bid_invitation_id": str(uuid4()),
            "bid_package_id": str(uuid4()),
            "task_id": str(uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.SUPABASE_JWT_SECRET,
        algorithm="HS256",
    )
    resp = await vendor_client.get(
        PROTECTED_PATH, headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


async def test_token_with_wrong_type_claim_is_rejected(vendor_client):
    """An admin-style token (type=authenticated) must not pass the type guard."""
    forged = jwt.encode(
        {
            "type": "authenticated",
            "sub": str(uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.VENDOR_JWT_SECRET,  # signed with the right secret
        algorithm=VENDOR_JWT_ALGORITHM,
    )
    resp = await vendor_client.get(
        PROTECTED_PATH, headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


async def test_expired_vendor_jwt_returns_401(vendor_client):
    expired = jwt.encode(
        {
            "type": VENDOR_TOKEN_TYPE,
            "vendor_id": str(uuid4()),
            "vendor_contact_id": str(uuid4()),
            "bid_invitation_id": str(uuid4()),
            "bid_package_id": str(uuid4()),
            "task_id": str(uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=5),
        },
        settings.VENDOR_JWT_SECRET,
        algorithm=VENDOR_JWT_ALGORITHM,
    )
    resp = await vendor_client.get(
        PROTECTED_PATH, headers={"Authorization": f"Bearer {expired}"}
    )
    assert resp.status_code == 401
