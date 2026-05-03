"""
Tests for POST /api/v1/vendor-auth/validate-token.

Each gate is exercised against real DB rows seeded by fixtures in
conftest.py. The endpoint's order of checks matters — earlier gates
short-circuit later ones — so each test sets up exactly one failing
gate to keep the assertions unambiguous.
"""

from __future__ import annotations

from datetime import datetime, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.vendor_auth import VENDOR_JWT_ALGORITHM, VENDOR_TOKEN_TYPE

VALIDATE_PATH = "/api/v1/vendor-auth/validate-token"


# ── Happy path ──────────────────────────────────────────────────────────


async def test_valid_token_returns_200_with_jwt_and_full_bid_context(
    vendor_client, valid_token_setup
):
    refs = valid_token_setup
    resp = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["jwt"], str) and body["jwt"].count(".") == 2

    ctx = body["bid_context"]
    assert ctx["vendor"]["id"] == refs.vendor_id
    assert ctx["project"]["id"] == refs.project_id
    assert ctx["task"]["id"] == refs.task_id
    assert ctx["bid_package"]["id"] == refs.bid_package_id
    assert ctx["bid_template"]["id"] == refs.bid_template_id
    assert {item["id"] for item in ctx["bid_template"]["items"]} == set(refs.template_item_ids)
    assert isinstance(ctx["project_documents"], list)
    assert ctx["existing_draft"] is None


async def test_jwt_payload_carries_required_claims_and_correct_lifetime(
    vendor_client, valid_token_setup
):
    refs = valid_token_setup
    resp = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert resp.status_code == 200

    payload = jwt.decode(
        resp.json()["jwt"], settings.VENDOR_JWT_SECRET, algorithms=[VENDOR_JWT_ALGORITHM]
    )
    assert payload["type"] == VENDOR_TOKEN_TYPE
    assert payload["vendor_id"] == refs.vendor_id
    assert payload["vendor_contact_id"] == refs.vendor_contact_id
    assert payload["bid_invitation_id"] == refs.bid_invitation_id
    assert payload["bid_package_id"] == refs.bid_package_id
    assert payload["task_id"] == refs.task_id
    assert payload["exp"] - payload["iat"] == settings.VENDOR_JWT_EXPIRY_HOURS * 3600


# ── Negative gates ──────────────────────────────────────────────────────


async def test_unknown_token_returns_404(vendor_client):
    resp = await vendor_client.post(VALIDATE_PATH, json={"token": "garbage-not-in-db"})
    assert resp.status_code == 404


async def test_expired_token_returns_410(vendor_client, expired_token_setup):
    resp = await vendor_client.post(
        VALIDATE_PATH, json={"token": expired_token_setup.raw_token}
    )
    assert resp.status_code == 410


@pytest.mark.parametrize("non_open_status", ["cancelled", "closed"])
async def test_non_open_package_returns_423(vendor_client, seed, non_open_status):
    refs = seed(package_status=non_open_status)
    resp = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert resp.status_code == 423


async def test_already_submitted_bid_returns_409(vendor_client, submitted_bid_setup):
    resp = await vendor_client.post(
        VALIDATE_PATH, json={"token": submitted_bid_setup.raw_token}
    )
    assert resp.status_code == 409


# ── Re-entry behavior (the corrected design) ────────────────────────────


async def test_reclick_after_token_marked_used_still_returns_200(
    vendor_client, used_token_setup
):
    """Re-entry is intentional: vendors re-click the magic link to resume after JWT expiry."""
    resp = await vendor_client.post(
        VALIDATE_PATH, json={"token": used_token_setup.raw_token}
    )
    assert resp.status_code == 200


async def test_reclick_does_not_overwrite_used_at(db, vendor_client, used_token_setup):
    refs = used_token_setup
    before = (
        db.table("magic_link_tokens")
        .select("used_at, ip_address")
        .eq("id", refs.magic_link_token_id)
        .single()
        .execute()
        .data
    )

    resp = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert resp.status_code == 200

    after = (
        db.table("magic_link_tokens")
        .select("used_at, ip_address")
        .eq("id", refs.magic_link_token_id)
        .single()
        .execute()
        .data
    )
    assert after["used_at"] == before["used_at"]
    assert after["ip_address"] == before["ip_address"]


# ── First-click audit ──────────────────────────────────────────────────


async def test_first_click_marks_token_used_with_timestamp_and_ip(
    db, vendor_client, valid_token_setup
):
    refs = valid_token_setup
    resp = await vendor_client.post(
        VALIDATE_PATH,
        json={"token": refs.raw_token},
        headers={"X-Forwarded-For": "198.51.100.42"},
    )
    assert resp.status_code == 200

    row = (
        db.table("magic_link_tokens")
        .select("is_used, used_at, ip_address")
        .eq("id", refs.magic_link_token_id)
        .single()
        .execute()
        .data
    )
    assert row["is_used"] is True
    assert row["used_at"] is not None
    assert row["ip_address"] is not None
    # ip_address is INET — Supabase returns it as a string with the recorded IP.
    assert "198.51.100.42" in str(row["ip_address"])


# ── Invitation 'opened' transition ─────────────────────────────────────


async def test_first_click_transitions_invitation_to_opened_and_stamps_opened_at(
    db, vendor_client, valid_token_setup
):
    refs = valid_token_setup
    resp = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert resp.status_code == 200

    row = (
        db.table("bid_invitations")
        .select("status, opened_at")
        .eq("id", refs.bid_invitation_id)
        .single()
        .execute()
        .data
    )
    assert row["status"] == "opened"
    assert row["opened_at"] is not None


async def test_reclick_does_not_advance_status_or_overwrite_opened_at(
    db, vendor_client, valid_token_setup
):
    refs = valid_token_setup

    first = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert first.status_code == 200
    after_first = (
        db.table("bid_invitations")
        .select("status, opened_at")
        .eq("id", refs.bid_invitation_id)
        .single()
        .execute()
        .data
    )
    assert after_first["status"] == "opened"
    assert after_first["opened_at"] is not None

    second = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert second.status_code == 200
    after_second = (
        db.table("bid_invitations")
        .select("status, opened_at")
        .eq("id", refs.bid_invitation_id)
        .single()
        .execute()
        .data
    )
    assert after_second["status"] == "opened"
    assert after_second["opened_at"] == after_first["opened_at"]


# ── Revocation gate (introduced with Resend Bid Link) ──────────────────


@pytest.mark.parametrize("token_is_used", [True, False])
async def test_validate_token_rejects_revoked_token(
    db, vendor_client, seed, admin_user_id, token_is_used
):
    """A token with revoked_at IS NOT NULL must return 410 regardless of
    its is_used state. This is the core gate added by the Resend Bid Link
    bug fix — revocation, not just consumption, is what bounds a token."""
    refs = seed(token_is_used=token_is_used)

    db.table("magic_link_tokens").update(
        {
            "revoked_at": datetime.now(timezone.utc).isoformat(),
            "revoked_by": admin_user_id,
        }
    ).eq("id", refs.magic_link_token_id).execute()

    resp = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert resp.status_code == 410


async def test_validate_token_accepts_used_but_not_revoked_token(
    vendor_client, seed
):
    """Re-click-to-resume must keep working: is_used=TRUE alone (with
    revoked_at NULL and a future expiry) still yields a 200 + JWT."""
    refs = seed(token_is_used=True)
    resp = await vendor_client.post(VALIDATE_PATH, json={"token": refs.raw_token})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("jwt"), str) and body["jwt"].count(".") == 2


# ── Rate limiting ──────────────────────────────────────────────────────


async def test_eleventh_request_from_same_ip_returns_429_with_retry_after(vendor_client):
    headers = {"X-Forwarded-For": "203.0.113.77"}
    payload = {"token": "garbage-token-just-for-rate-limit"}

    # First 10 attempts may fail (404) but should not be rate-limited.
    for _ in range(10):
        resp = await vendor_client.post(VALIDATE_PATH, json=payload, headers=headers)
        assert resp.status_code != 429

    resp = await vendor_client.post(VALIDATE_PATH, json=payload, headers=headers)
    assert resp.status_code == 429
    assert "retry-after" in {k.lower() for k in resp.headers.keys()}
