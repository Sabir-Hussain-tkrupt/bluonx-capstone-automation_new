"""
JWT isolation between the bid and milestone vendor surfaces (Phase 10.2).

A milestone token must never satisfy a bid endpoint and vice versa, even though
both are signed with VENDOR_JWT_SECRET and carry type='vendor_portal'. The
guard is the presence/absence of the milestone_alert_id claim, asserted by the
two dependencies.
"""

from __future__ import annotations

from uuid import uuid4

from app.core.vendor_auth import VendorContext, issue_vendor_jwt

MS_PATH = "/api/v1/__ms_test__/milestone"
BID_PATH = "/api/v1/__ms_test__/bid"


def _milestone_ctx() -> VendorContext:
    return VendorContext(
        vendor_id=uuid4(),
        vendor_contact_id=uuid4(),
        milestone_alert_id=uuid4(),
        milestone_id=uuid4(),
        cycle_number=3,
    )


def _bid_ctx() -> VendorContext:
    return VendorContext(
        vendor_id=uuid4(),
        vendor_contact_id=uuid4(),
        bid_invitation_id=uuid4(),
        bid_package_id=uuid4(),
        task_id=uuid4(),
    )


async def test_milestone_jwt_satisfies_milestone_endpoint(auth_client):
    ctx = _milestone_ctx()
    token = issue_vendor_jwt(ctx)
    resp = await auth_client.get(MS_PATH, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["vendor_id"] == str(ctx.vendor_id)
    assert body["milestone_alert_id"] == str(ctx.milestone_alert_id)
    assert body["milestone_id"] == str(ctx.milestone_id)
    assert body["cycle_number"] == ctx.cycle_number


async def test_bid_jwt_rejected_by_milestone_endpoint(auth_client):
    token = issue_vendor_jwt(_bid_ctx())
    resp = await auth_client.get(MS_PATH, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_milestone_jwt_rejected_by_bid_endpoint(auth_client):
    token = issue_vendor_jwt(_milestone_ctx())
    resp = await auth_client.get(BID_PATH, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_bid_jwt_still_satisfies_bid_endpoint(auth_client):
    """Regression: the bid path is unchanged for bid tokens."""
    ctx = _bid_ctx()
    token = issue_vendor_jwt(ctx)
    resp = await auth_client.get(BID_PATH, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["vendor_id"] == str(ctx.vendor_id)


def test_milestone_jwt_carries_no_bid_claims():
    """A milestone token must not leak bid claims into the payload."""
    import jwt

    from app.core.config import settings
    from app.core.vendor_auth import VENDOR_JWT_ALGORITHM

    token = issue_vendor_jwt(_milestone_ctx())
    payload = jwt.decode(
        token, settings.VENDOR_JWT_SECRET, algorithms=[VENDOR_JWT_ALGORITHM]
    )
    assert "milestone_alert_id" in payload
    assert "bid_invitation_id" not in payload
    assert "bid_package_id" not in payload
    assert "task_id" not in payload
