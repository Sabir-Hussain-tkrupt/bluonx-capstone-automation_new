"""Pure unit tests for vendor JWT signing/decoding."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.vendor_auth import (
    VENDOR_JWT_ALGORITHM,
    VENDOR_TOKEN_TYPE,
    VendorContext,
    issue_vendor_jwt,
)


def _ctx() -> VendorContext:
    return VendorContext(
        vendor_id=uuid4(),
        vendor_contact_id=uuid4(),
        bid_invitation_id=uuid4(),
        bid_package_id=uuid4(),
        task_id=uuid4(),
    )


def test_issue_vendor_jwt_payload_matches_claims_and_expiry_window():
    ctx = _ctx()
    before = datetime.now(timezone.utc)
    token = issue_vendor_jwt(ctx)
    payload = jwt.decode(token, settings.VENDOR_JWT_SECRET, algorithms=[VENDOR_JWT_ALGORITHM])

    assert payload["type"] == VENDOR_TOKEN_TYPE
    assert payload["vendor_id"] == str(ctx.vendor_id)
    assert payload["vendor_contact_id"] == str(ctx.vendor_contact_id)
    assert payload["bid_invitation_id"] == str(ctx.bid_invitation_id)
    assert payload["bid_package_id"] == str(ctx.bid_package_id)
    assert payload["task_id"] == str(ctx.task_id)

    expected_lifetime = settings.VENDOR_JWT_EXPIRY_HOURS * 3600
    assert payload["exp"] - payload["iat"] == expected_lifetime
    assert payload["iat"] >= int(before.timestamp()) - 1


def test_decode_with_wrong_secret_raises_invalid_signature():
    token = issue_vendor_jwt(_ctx())
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "definitely-not-the-real-secret", algorithms=[VENDOR_JWT_ALGORITHM])


def test_decode_expired_token_raises_expired_signature():
    expired = jwt.encode(
        {
            "type": VENDOR_TOKEN_TYPE,
            "vendor_id": "x",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=5),
        },
        settings.VENDOR_JWT_SECRET,
        algorithm=VENDOR_JWT_ALGORITHM,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(expired, settings.VENDOR_JWT_SECRET, algorithms=[VENDOR_JWT_ALGORITHM])


def test_round_trip_preserves_every_id_field():
    ctx = _ctx()
    token = issue_vendor_jwt(ctx)
    payload = jwt.decode(token, settings.VENDOR_JWT_SECRET, algorithms=[VENDOR_JWT_ALGORITHM])

    rebuilt_ids = {
        "vendor_id": payload["vendor_id"],
        "vendor_contact_id": payload["vendor_contact_id"],
        "bid_invitation_id": payload["bid_invitation_id"],
        "bid_package_id": payload["bid_package_id"],
        "task_id": payload["task_id"],
    }
    expected = {
        "vendor_id": str(ctx.vendor_id),
        "vendor_contact_id": str(ctx.vendor_contact_id),
        "bid_invitation_id": str(ctx.bid_invitation_id),
        "bid_package_id": str(ctx.bid_package_id),
        "task_id": str(ctx.task_id),
    }
    assert rebuilt_ids == expected
