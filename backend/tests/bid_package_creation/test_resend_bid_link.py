"""
Resend Bid Link tests.

Verifies the resend flow under the new name and revocation rules:
  - prior tokens are HARD-revoked (revoked_at + revoked_by stamped)
    in addition to the soft is_used flag,
  - a single new token is inserted with revoked_at left NULL,
  - the invitation's sent_at is refreshed but its status / opened_at
    are preserved (re-clicks resume the previously-opened state),
  - non-open bid packages and missing rows are rejected without
    side effects,
  - a missing vendor_contact yields 404 (no silent empty-string fallback),
  - the email subject reflects the rename ("Bid Link (Resent)").

These tests intentionally import the renamed function `resend_bid_link`
which does not yet exist — the module-level import will fail until the
service is renamed, putting every test in this file into the RED state
for the right reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from .conftest import (
    BID_TEMPLATE_ID,
    PM_USER_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

# Import will fail until the rename + revocation refactor lands — that is
# the expected RED state.
from app.services.bid_package_service import (  # noqa: E402
    BidPackageValidationError,
    resend_bid_link,
)


INVITATION_ID = uuid4()
BID_PACKAGE_ID = uuid4()


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def sample_invitation_sent() -> dict:
    """Invitation in 'sent' state — never opened."""
    return {
        "id": str(INVITATION_ID),
        "bid_package_id": str(BID_PACKAGE_ID),
        "vendor_id": str(VENDOR_IDS[0]),
        "vendor_contact_id": str(VENDOR_CONTACT_IDS[0]),
        "status": "sent",
        "sent_at": (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat(),
        "opened_at": None,
    }


@pytest.fixture()
def sample_invitation_opened() -> dict:
    """Invitation in 'opened' state — vendor already viewed the link once."""
    opened_at = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    return {
        "id": str(INVITATION_ID),
        "bid_package_id": str(BID_PACKAGE_ID),
        "vendor_id": str(VENDOR_IDS[0]),
        "vendor_contact_id": str(VENDOR_CONTACT_IDS[0]),
        "status": "opened",
        "sent_at": (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat(),
        "opened_at": opened_at,
    }


@pytest.fixture()
def sample_bid_package_open() -> dict:
    deadline = datetime.now(timezone.utc) + timedelta(days=14)
    return {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": deadline.isoformat(),
        "status": "open",
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
    }


@pytest.fixture()
def one_existing_token() -> list[dict]:
    return [
        {
            "id": str(uuid4()),
            "bid_invitation_id": str(INVITATION_ID),
            "vendor_id": str(VENDOR_IDS[0]),
            "token_hash": "hash_old_1",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "is_used": False,
            "revoked_at": None,
            "revoked_by": None,
        }
    ]


@pytest.fixture()
def three_existing_tokens() -> list[dict]:
    base_expires = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    rows = []
    for i in range(3):
        rows.append(
            {
                "id": str(uuid4()),
                "bid_invitation_id": str(INVITATION_ID),
                "vendor_id": str(VENDOR_IDS[0]),
                "token_hash": f"hash_old_{i}",
                "expires_at": base_expires,
                "is_used": i == 0,  # mix of used and unused prior tokens
                "revoked_at": None,
                "revoked_by": None,
            }
        )
    return rows


# ── Mock wiring helper ─────────────────────────────────────────────────


def _setup_resend_mocks(
    mock_supabase,
    invitation: dict | None,
    bid_package: dict | None,
    tokens: list[dict],
    *,
    contact: dict | None = None,
    contact_present: bool = True,
):
    """Configure per-table mock chains for the resend flow.

    Returns (token_updates, token_inserts, invitation_updates) so tests
    can assert on every captured write payload.
    """
    token_updates: list[dict] = []
    token_inserts: list[dict] = []
    invitation_updates: list[dict] = []

    default_contact = {
        "id": str(VENDOR_CONTACT_IDS[0]),
        "vendor_id": str(VENDOR_IDS[0]),
        "full_name": "John Smith",
        "email": "john@smithgrading.com",
    }
    use_contact = contact if contact is not None else default_contact

    def table_side_effect(table_name):
        chain = MagicMock()

        if table_name == "bid_invitations":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(
                data=[invitation] if invitation else []
            )

            def capture_invitation_update(payload):
                invitation_updates.append(payload)
                u = MagicMock()
                u.eq.return_value = u
                u.execute.return_value = MagicMock(
                    data=[invitation] if invitation else []
                )
                return u

            chain.update.side_effect = capture_invitation_update
        elif table_name == "bid_packages":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(
                data=[bid_package] if bid_package else []
            )
        elif table_name == "magic_link_tokens":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.execute.return_value = MagicMock(data=tokens)

            def capture_token_update(payload):
                token_updates.append(payload)
                u = MagicMock()
                u.eq.return_value = u
                u.is_.return_value = u
                u.execute.return_value = MagicMock(data=[])
                return u

            chain.update.side_effect = capture_token_update

            def capture_token_insert(row):
                token_inserts.append(row)
                u = MagicMock()
                u.execute.return_value = MagicMock(
                    data=[{**row, "id": str(uuid4())}]
                )
                return u

            chain.insert.side_effect = capture_token_insert
        elif table_name == "vendor_contacts":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(
                data=[use_contact] if contact_present else []
            )
        else:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[])
            chain.insert.return_value = chain
            chain.update.return_value = chain

        return chain

    mock_supabase.table.side_effect = table_side_effect
    return token_updates, token_inserts, invitation_updates


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resend_bid_link_creates_new_token_and_revokes_old(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_sent,
    sample_bid_package_open,
    one_existing_token,
):
    """Old token is hard-revoked (revoked_at + revoked_by); new token is live."""
    token_updates, token_inserts, _ = _setup_resend_mocks(
        mock_supabase,
        sample_invitation_sent,
        sample_bid_package_open,
        one_existing_token,
    )

    await resend_bid_link(
        invitation_id=INVITATION_ID,
        current_user_id=PM_USER_ID,
        db=mock_supabase,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    revoking_updates = [
        u for u in token_updates if u.get("revoked_at") is not None
    ]
    assert revoking_updates, (
        f"Expected an update setting revoked_at on prior tokens; got {token_updates}"
    )
    assert all(
        u.get("revoked_by") is not None for u in revoking_updates
    ), f"revoked_by must be set whenever revoked_at is; got {revoking_updates}"

    assert len(token_inserts) == 1, "Exactly one new token row must be inserted"
    new_row = token_inserts[0]
    assert new_row["bid_invitation_id"] == str(INVITATION_ID)
    assert new_row.get("revoked_at") is None, (
        f"Newly inserted token must have revoked_at=NULL; got {new_row}"
    )


@pytest.mark.asyncio
async def test_resend_bid_link_revokes_multiple_prior_tokens(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_sent,
    sample_bid_package_open,
    three_existing_tokens,
):
    """All three prior tokens must be revoked; only the newest remains live."""
    token_updates, token_inserts, _ = _setup_resend_mocks(
        mock_supabase,
        sample_invitation_sent,
        sample_bid_package_open,
        three_existing_tokens,
    )

    await resend_bid_link(
        invitation_id=INVITATION_ID,
        current_user_id=PM_USER_ID,
        db=mock_supabase,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    # A bulk update keyed on bid_invitation_id is acceptable — one update
    # payload covers all three rows. What matters is that revoked_at +
    # revoked_by were set in at least one captured update payload.
    assert any(
        u.get("revoked_at") is not None and u.get("revoked_by") is not None
        for u in token_updates
    ), f"Expected revoked_at + revoked_by in token updates; got {token_updates}"

    assert len(token_inserts) == 1, "Only one new live token allowed"
    assert token_inserts[0].get("revoked_at") is None


@pytest.mark.asyncio
async def test_resend_bid_link_updates_sent_at_but_not_status_or_opened_at(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_opened,
    sample_bid_package_open,
    one_existing_token,
):
    """Resending an already-opened invitation must not regress status or
    overwrite opened_at — only sent_at is refreshed."""
    _, _, invitation_updates = _setup_resend_mocks(
        mock_supabase,
        sample_invitation_opened,
        sample_bid_package_open,
        one_existing_token,
    )

    await resend_bid_link(
        invitation_id=INVITATION_ID,
        current_user_id=PM_USER_ID,
        db=mock_supabase,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    assert invitation_updates, "Expected at least one bid_invitations update"

    merged: dict = {}
    for payload in invitation_updates:
        merged.update(payload)

    assert "sent_at" in merged, f"sent_at must be refreshed; got {merged}"
    assert "status" not in merged, (
        f"status must not be touched on resend; got {merged}"
    )
    assert "opened_at" not in merged, (
        f"opened_at must not be touched on resend; got {merged}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["closed", "cancelled", "evaluating"])
async def test_resend_bid_link_rejects_when_package_not_open(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_sent,
    one_existing_token,
    status,
):
    """Non-open package → 400, no token writes, no email sent."""
    pkg = {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "status": status,
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
    }
    token_updates, token_inserts, _ = _setup_resend_mocks(
        mock_supabase, sample_invitation_sent, pkg, one_existing_token
    )

    with pytest.raises(BidPackageValidationError) as exc_info:
        await resend_bid_link(
            invitation_id=INVITATION_ID,
            current_user_id=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

    assert exc_info.value.status_code == 400
    assert token_inserts == [], "No new token may be inserted on rejection"
    assert not any(
        u.get("revoked_at") is not None for u in token_updates
    ), f"Prior tokens must NOT be revoked on rejection; got {token_updates}"
    assert mock_email_service.send_email.call_count == 0


@pytest.mark.asyncio
async def test_resend_bid_link_404_when_invitation_missing(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
):
    """Unknown invitation_id → 404."""
    _setup_resend_mocks(mock_supabase, invitation=None, bid_package=None, tokens=[])

    with pytest.raises(BidPackageValidationError) as exc_info:
        await resend_bid_link(
            invitation_id=uuid4(),
            current_user_id=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

    assert exc_info.value.status_code == 404
    assert mock_email_service.send_email.call_count == 0


@pytest.mark.asyncio
async def test_resend_bid_link_404_when_vendor_contact_missing(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_sent,
    sample_bid_package_open,
    one_existing_token,
):
    """Defensive: a deleted/missing vendor_contact must surface as 404,
    not silently send an email to ''."""
    _setup_resend_mocks(
        mock_supabase,
        sample_invitation_sent,
        sample_bid_package_open,
        one_existing_token,
        contact_present=False,
    )

    with pytest.raises(BidPackageValidationError) as exc_info:
        await resend_bid_link(
            invitation_id=INVITATION_ID,
            current_user_id=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

    assert exc_info.value.status_code == 404
    assert mock_email_service.send_email.call_count == 0, (
        "Email must NOT be sent when the contact lookup fails"
    )


@pytest.fixture()
def sample_invitation_send_failed() -> dict:
    """Invitation whose initial email failed — never delivered."""
    return {
        "id": str(INVITATION_ID),
        "bid_package_id": str(BID_PACKAGE_ID),
        "vendor_id": str(VENDOR_IDS[0]),
        "vendor_contact_id": str(VENDOR_CONTACT_IDS[0]),
        "status": "send_failed",
        "sent_at": None,
        "opened_at": None,
    }


@pytest.mark.asyncio
async def test_resend_reconciles_send_failed_to_sent_on_success(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_send_failed,
    sample_bid_package_open,
    one_existing_token,
):
    """A never-delivered (send_failed) invitation is flipped to 'sent' (with
    sent_at) once the resend succeeds, and the subject is a first-send subject,
    not '(Resent)'."""
    _, _, invitation_updates = _setup_resend_mocks(
        mock_supabase,
        sample_invitation_send_failed,
        sample_bid_package_open,
        one_existing_token,
    )

    await resend_bid_link(
        invitation_id=INVITATION_ID,
        current_user_id=PM_USER_ID,
        db=mock_supabase,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    merged: dict = {}
    for payload in invitation_updates:
        merged.update(payload)
    assert merged.get("status") == "sent", f"send_failed should flip to sent; got {merged}"
    assert "sent_at" in merged

    subject = mock_email_service.send_email.call_args.kwargs.get("subject", "")
    assert subject.startswith("Bid Invitation:"), (
        f"A never-delivered invitation is a first send, not a resend; got {subject!r}"
    )
    assert subject != "Bid Link (Resent)"


@pytest.mark.asyncio
async def test_resend_keeps_send_failed_when_email_fails_again(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_send_failed,
    sample_bid_package_open,
    one_existing_token,
):
    """If the resend also fails, the invitation stays 'send_failed'."""
    from app.services.email_service import EmailSendResult

    mock_email_service.send_email.return_value = EmailSendResult(
        message_id=f"mock-{uuid4()}", status="failed", error="still rejected",
    )

    _, _, invitation_updates = _setup_resend_mocks(
        mock_supabase,
        sample_invitation_send_failed,
        sample_bid_package_open,
        one_existing_token,
    )

    await resend_bid_link(
        invitation_id=INVITATION_ID,
        current_user_id=PM_USER_ID,
        db=mock_supabase,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    merged: dict = {}
    for payload in invitation_updates:
        merged.update(payload)
    assert merged.get("status") == "send_failed", (
        f"A failed resend must leave status at send_failed; got {merged}"
    )


@pytest.mark.asyncio
async def test_resend_bid_link_email_subject_is_updated(
    mock_supabase,
    mock_email_service,
    mock_template_renderer,
    sample_invitation_sent,
    sample_bid_package_open,
    one_existing_token,
):
    """Subject reflects the rename: 'Bid Link (Resent)'."""
    _setup_resend_mocks(
        mock_supabase,
        sample_invitation_sent,
        sample_bid_package_open,
        one_existing_token,
    )

    await resend_bid_link(
        invitation_id=INVITATION_ID,
        current_user_id=PM_USER_ID,
        db=mock_supabase,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    assert mock_email_service.send_email.call_count == 1
    kwargs = mock_email_service.send_email.call_args.kwargs
    assert kwargs.get("subject") == "Bid Link (Resent)", (
        f"Expected updated subject 'Bid Link (Resent)'; got {kwargs.get('subject')!r}"
    )
