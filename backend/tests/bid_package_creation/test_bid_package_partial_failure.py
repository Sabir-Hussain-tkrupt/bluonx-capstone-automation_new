"""
Partial failure tests for bid package creation.

The DB rows are written atomically by the creation RPC (all invitations start as
'pending_send'). Emails are then sent best-effort: a send failure for one vendor
must not block the others, and each invitation must be reconciled to its real
outcome -- 'sent' on success, 'send_failed' on failure -- so the row is never
left falsely reading 'sent'.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult

from .conftest import (
    BID_TEMPLATE_ID,
    PM_USER_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

from app.services.bid_package_service import create_bid_package_with_invitations


# The email address that will trigger a simulated failure (vendor index 1).
FAILING_EMAIL = "maria@apexearth.com"


def _make_email_service_with_one_failure() -> AsyncMock:
    """Create a mock email service where one specific vendor's email fails."""
    service = AsyncMock()

    async def conditional_send(**kwargs):
        to_email = kwargs.get("to_email", "")
        if to_email == FAILING_EMAIL:
            return EmailSendResult(
                message_id=f"mock-{uuid4()}",
                status="failed",
                error="MessageRejected: Email address is not verified",
            )
        return EmailSendResult(
            message_id=f"mock-{uuid4()}",
            status="sent",
            error=None,
        )

    service.send_email.side_effect = conditional_send
    return service


def _setup_creation_mocks(mock_supabase):
    """Wire the creation RPC (deterministic invitation ids), the vendor/contact
    lookups the email phase needs, and capture of bid_invitations status
    reconciliation updates.

    Returns `reconciled`, a list of (invitation_id, status) tuples recorded as
    the service flips each invitation to 'sent' / 'send_failed'.
    """
    reconciled: list[tuple[str, str]] = []

    def _rpc(fn_name, params=None):
        result = MagicMock()
        if fn_name == "fn_create_bid_package_with_invitations":
            vendors = (params or {}).get("p_vendors", [])
            result.execute.return_value = MagicMock(data={
                "bid_package_id": str(uuid4()),
                "round_number": 1,
                # Deterministic id per vendor so the test can map outcomes back.
                "invitations": [
                    {"vendor_id": v["vendor_id"], "invitation_id": f"inv-{v['vendor_id']}"}
                    for v in vendors
                ],
            })
        else:
            result.execute.return_value = MagicMock(data=None)
        return result

    mock_supabase.rpc.side_effect = _rpc

    _vendors_by_id = {
        str(VENDOR_IDS[0]): {"id": str(VENDOR_IDS[0]), "company_name": "Smith Grading Co.", "status": "active", "deleted_at": None},
        str(VENDOR_IDS[1]): {"id": str(VENDOR_IDS[1]), "company_name": "Apex Earthworks", "status": "active", "deleted_at": None},
        str(VENDOR_IDS[2]): {"id": str(VENDOR_IDS[2]), "company_name": "Summit Sitework", "status": "active", "deleted_at": None},
    }
    _contacts_by_id = {
        str(VENDOR_CONTACT_IDS[0]): {"id": str(VENDOR_CONTACT_IDS[0]), "vendor_id": str(VENDOR_IDS[0]), "full_name": "John Smith", "email": "john@smithgrading.com"},
        str(VENDOR_CONTACT_IDS[1]): {"id": str(VENDOR_CONTACT_IDS[1]), "vendor_id": str(VENDOR_IDS[1]), "full_name": "Maria Garcia", "email": FAILING_EMAIL},
        str(VENDOR_CONTACT_IDS[2]): {"id": str(VENDOR_CONTACT_IDS[2]), "vendor_id": str(VENDOR_IDS[2]), "full_name": "David Chen", "email": "david@summitsite.com"},
    }

    def table_side_effect(table_name):
        chain = MagicMock()

        if table_name == "bid_invitations":
            # Capture the reconciliation: update({...}).eq("id", id).execute()
            def _update(payload):
                upd = MagicMock()

                def _eq(field, value):
                    eqm = MagicMock()

                    def _execute():
                        reconciled.append((str(value), payload.get("status")))
                        return MagicMock(data=[])

                    eqm.execute.side_effect = _execute
                    return eqm

                upd.eq.side_effect = _eq
                return upd

            chain.update.side_effect = _update
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[])
        elif table_name == "vendors":
            def vendors_eq(field, value):
                vendor = _vendors_by_id.get(str(value))
                result = MagicMock()
                result.single.return_value = result
                result.eq.return_value = result
                result.execute.return_value = MagicMock(data=[vendor] if vendor else [])
                return result
            chain.select.return_value = chain
            chain.eq.side_effect = vendors_eq
        elif table_name == "vendor_contacts":
            def contacts_eq(field, value):
                contact = _contacts_by_id.get(str(value))
                result = MagicMock()
                result.single.return_value = result
                result.eq.return_value = result
                result.execute.return_value = MagicMock(data=[contact] if contact else [])
                return result
            chain.select.return_value = chain
            chain.eq.side_effect = contacts_eq
        else:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.is_.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[])

        return chain

    mock_supabase.table.side_effect = table_side_effect
    return reconciled


def _payload(future_deadline) -> dict:
    return {
        "task_id": str(TASK_ID),
        "bid_template_id": str(BID_TEMPLATE_ID),
        "deadline": future_deadline.isoformat(),
        "project_document_ids": [],
        "vendor_selections": [
            {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
            for i in range(3)
        ],
    }


class TestPartialEmailFailure:
    """When one vendor's email fails, the rest should still succeed."""

    @pytest.mark.asyncio
    async def test_other_vendors_still_get_emails(
        self, mock_supabase, mock_template_renderer, future_deadline,
    ):
        """If email fails for vendor 2, vendors 1 and 3 still get their emails."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase)

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        assert email_service.send_email.call_count == 3
        assert result["invitations_sent"] == 2
        assert result["invitations_failed"] == 1

    @pytest.mark.asyncio
    async def test_all_rows_created_in_one_atomic_rpc(
        self, mock_supabase, mock_template_renderer, future_deadline,
    ):
        """All 3 invitations + tokens are created in a single atomic RPC call,
        regardless of email outcome."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase)

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        rpc_calls = [
            c
            for c in mock_supabase.rpc.call_args_list
            if c.args and c.args[0] == "fn_create_bid_package_with_invitations"
        ]
        assert len(rpc_calls) == 1
        assert len(rpc_calls[0].args[1]["p_vendors"]) == 3

    @pytest.mark.asyncio
    async def test_failed_vendor_reconciled_to_send_failed(
        self, mock_supabase, mock_template_renderer, future_deadline,
    ):
        """The failed vendor's invitation is flipped to 'send_failed'; the two
        successful ones to 'sent'. Nothing is left falsely reading 'sent'."""
        email_service = _make_email_service_with_one_failure()
        reconciled = _setup_creation_mocks(mock_supabase)

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        outcomes = dict(reconciled)
        failed_inv = f"inv-{VENDOR_IDS[1]}"
        sent_inv_0 = f"inv-{VENDOR_IDS[0]}"
        sent_inv_2 = f"inv-{VENDOR_IDS[2]}"

        assert outcomes[failed_inv] == "send_failed"
        assert outcomes[sent_inv_0] == "sent"
        assert outcomes[sent_inv_2] == "sent"

    @pytest.mark.asyncio
    async def test_failed_vendor_in_response_with_error(
        self, mock_supabase, mock_template_renderer, future_deadline,
    ):
        """The failed vendor appears in failed_vendors with an error reason."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase)

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(result["failed_vendors"]) == 1
        failed = result["failed_vendors"][0]
        assert failed["vendor_id"] == str(VENDOR_IDS[1])
        assert failed["error"]

    @pytest.mark.asyncio
    async def test_response_counts_are_correct(
        self, mock_supabase, mock_template_renderer, future_deadline,
    ):
        """Response shows correct invitations_sent and invitations_failed."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase)

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        assert result["invitations_sent"] == 2
        assert result["invitations_failed"] == 1
        assert result["invitations_sent"] + result["invitations_failed"] == 3
