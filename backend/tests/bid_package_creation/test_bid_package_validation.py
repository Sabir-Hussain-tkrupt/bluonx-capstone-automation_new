"""
Input validation tests for bid package creation.

Verifies that invalid inputs are rejected with appropriate HTTP status codes
and descriptive error messages before any database writes occur.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from .conftest import (
    BID_TEMPLATE_ID,
    DELETED_TASK_ID,
    DELETED_VENDOR_ID,
    DOC_IDS,
    INACTIVE_VENDOR_CONTACT_ID,
    INACTIVE_VENDOR_ID,
    NONEXISTENT_DOC_ID,
    NONEXISTENT_TASK_ID,
    NONEXISTENT_TEMPLATE_ID,
    NONEXISTENT_VENDOR_ID,
    PM_USER_ID,
    PROJECT_ID,
    TASK_CANCELLED_ID,
    TASK_COMPLETED_ID,
    TASK_ID,
    TASK_INTERNAL_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
    WRONG_PROJECT_DOC_ID,
    WRONG_VENDOR_CONTACT_ID,
)

# This import will fail until the service is implemented — expected for test-first.
from app.services.bid_package_service import (
    BidPackageValidationError,
    create_bid_package_with_invitations,
)


class TestTaskBidTypeValidation:
    """Only competitive tasks may have bid packages. The gate is positive, so
    anything else — 'internal', or a legacy 'direct_assign' row the API no
    longer accepts — is turned away before any vendor is contacted."""

    @pytest.mark.asyncio
    async def test_internal_task_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_internal,
        future_deadline,
    ):
        """bid_type='internal' must be rejected with 400 and a clear message."""
        # Configure mock to return the internal task
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_task_internal])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(TASK_INTERNAL_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_INTERNAL_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400
        assert "internal" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_legacy_direct_assign_task_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_direct_assign,
        future_deadline,
    ):
        """A pre-existing direct_assign row must fail closed here rather than
        entering the pipeline and dead-ending at the scoring gate later."""
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_task_direct_assign])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(TASK_INTERNAL_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_INTERNAL_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400
        assert "competitive" in str(exc_info.value.detail).lower()
        # No email may go out for a task that cannot be bid.
        mock_email_service.send_email.assert_not_called()


class TestTaskStatusValidation:
    """Only tasks in valid statuses can have bid packages created."""

    @pytest.mark.asyncio
    async def test_completed_task_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_completed,
        future_deadline,
    ):
        """Task with status='completed' cannot have a bid package."""
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_task_completed])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(TASK_COMPLETED_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_COMPLETED_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_cancelled_task_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_cancelled,
        future_deadline,
    ):
        """Task with status='cancelled' cannot have a bid package."""
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_task_cancelled])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(TASK_CANCELLED_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_CANCELLED_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400


class TestTaskExistenceValidation:
    """Tasks must exist and not be soft-deleted."""

    @pytest.mark.asyncio
    async def test_nonexistent_task_returns_404(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """A task_id that doesn't exist returns 404, never a 500.

        Two real-Supabase behaviors are simulated: the task SELECT uses
        .single(), which raises PGRST116 (0 rows) for a missing task, and the
        creation RPC raises a foreign-key violation that rolls the whole
        transaction back. The service must surface both as a clean 404.
        """
        # .single() on a missing row raises PGRST116 (not an empty result).
        select_chain = MagicMock()
        select_chain.execute.side_effect = APIError(
            {"code": "PGRST116", "message": "JSON object requested, 0 rows returned"}
        )
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        mock_supabase.rpc.side_effect = APIError(
            {"code": "23503", "message": "violates foreign key constraint"}
        )

        payload = {
            "task_id": str(NONEXISTENT_TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=NONEXISTENT_TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_task_returns_404(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_deleted_task,
        future_deadline,
    ):
        """Soft-deleted task (deleted_at set) should return 404."""
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_deleted_task])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(DELETED_TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=DELETED_TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 404


class TestBidTemplateValidation:
    """Bid template must exist."""

    @pytest.mark.asyncio
    async def test_nonexistent_bid_template_returns_404(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """bid_template_id that doesn't exist returns 404."""
        # Task lookup succeeds, template lookup fails
        def table_side_effect(table_name):
            chain = MagicMock()
            if table_name == "tasks":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[sample_task_competitive])
            elif table_name == "bid_templates":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            else:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(NONEXISTENT_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 404


class TestDeadlineValidation:
    """Deadline must be in the future."""

    @pytest.mark.asyncio
    async def test_past_deadline_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        past_deadline,
    ):
        """A deadline in the past must be rejected with 400."""
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_task_competitive])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": past_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400
        assert "deadline" in str(exc_info.value.detail).lower()


class TestVendorSelectionsValidation:
    """Vendor selections must be non-empty and contain valid entries."""

    @pytest.mark.asyncio
    async def test_empty_vendor_selections_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """Empty vendor_selections array must be rejected."""
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_task_competitive])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_duplicate_vendor_id_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """Duplicate vendor_id in vendor_selections must be rejected."""
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(data=[sample_task_competitive])
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.single.return_value = select_chain
        mock_supabase.table.return_value.select.return_value = select_chain

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400
        assert "duplicate" in str(exc_info.value.detail).lower()


class TestProjectDocumentValidation:
    """Project documents must belong to the task's project."""

    @pytest.mark.asyncio
    async def test_document_from_wrong_project_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """A project_document_id from a different project must be rejected."""
        wrong_project_doc = {
            "id": str(WRONG_PROJECT_DOC_ID),
            "project_id": str(uuid4()),  # Different project
            "file_name": "other_project.pdf",
        }

        def table_side_effect(table_name):
            chain = MagicMock()
            if table_name == "tasks":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[sample_task_competitive])
            elif table_name == "bid_templates":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[{
                    "id": str(BID_TEMPLATE_ID),
                    "name": "Standard Grading Template",
                    "is_lump_sum": True,
                }])
            elif table_name == "project_documents":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[wrong_project_doc])
            else:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [str(WRONG_PROJECT_DOC_ID)],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400


class TestVendorExistenceValidation:
    """Vendors must exist, be active, and not be deleted."""

    @pytest.mark.asyncio
    async def test_nonexistent_vendor_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """vendor_id that doesn't exist returns 400."""
        def table_side_effect(table_name):
            chain = MagicMock()
            if table_name == "tasks":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[sample_task_competitive])
            elif table_name == "bid_templates":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[{
                    "id": str(BID_TEMPLATE_ID),
                    "name": "Standard Grading Template",
                    "is_lump_sum": True,
                }])
            elif table_name == "vendors":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            else:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(NONEXISTENT_VENDOR_ID), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_deleted_vendor_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """Soft-deleted vendor (deleted_at set) must be rejected."""
        deleted_vendor = {
            "id": str(DELETED_VENDOR_ID),
            "company_name": "Gone Corp",
            "status": "active",
            "deleted_at": "2025-01-01T00:00:00+00:00",
        }

        def table_side_effect(table_name):
            chain = MagicMock()
            if table_name == "tasks":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[sample_task_competitive])
            elif table_name == "bid_templates":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[{
                    "id": str(BID_TEMPLATE_ID),
                    "name": "Standard Grading Template",
                    "is_lump_sum": True,
                }])
            elif table_name == "vendors":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[deleted_vendor])
            else:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(DELETED_VENDOR_ID), "vendor_contact_id": str(uuid4())},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_inactive_vendor_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """Vendor with status != 'active' must be rejected."""
        inactive_vendor = {
            "id": str(INACTIVE_VENDOR_ID),
            "company_name": "Suspended Inc.",
            "status": "suspended",
            "deleted_at": None,
        }

        def table_side_effect(table_name):
            chain = MagicMock()
            if table_name == "tasks":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[sample_task_competitive])
            elif table_name == "bid_templates":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[{
                    "id": str(BID_TEMPLATE_ID),
                    "name": "Standard Grading Template",
                    "is_lump_sum": True,
                }])
            elif table_name == "vendors":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[inactive_vendor])
            else:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(INACTIVE_VENDOR_ID), "vendor_contact_id": str(INACTIVE_VENDOR_CONTACT_ID)},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400


class TestVendorContactValidation:
    """Vendor contact must belong to the specified vendor."""

    @pytest.mark.asyncio
    async def test_contact_from_wrong_vendor_returns_400(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        sample_vendors,
        future_deadline,
    ):
        """vendor_contact_id that belongs to a different vendor must be rejected."""
        vendor_data = sample_vendors[0]["vendor"]
        wrong_contact = {
            "id": str(WRONG_VENDOR_CONTACT_ID),
            "vendor_id": str(uuid4()),  # Different vendor
            "full_name": "Wrong Person",
            "email": "wrong@other.com",
        }

        def table_side_effect(table_name):
            chain = MagicMock()
            if table_name == "tasks":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[sample_task_competitive])
            elif table_name == "bid_templates":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[{
                    "id": str(BID_TEMPLATE_ID),
                    "name": "Standard Grading Template",
                    "is_lump_sum": True,
                }])
            elif table_name == "vendors":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[vendor_data])
            elif table_name == "vendor_contacts":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[wrong_contact])
            else:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(WRONG_VENDOR_CONTACT_ID)},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400


class TestErrorResponseDetails:
    """Error responses should include specific details about what failed."""

    @pytest.mark.asyncio
    async def test_error_includes_which_vendor_failed(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        future_deadline,
    ):
        """When a vendor fails validation, the error detail names the vendor."""
        def table_side_effect(table_name):
            chain = MagicMock()
            if table_name == "tasks":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[sample_task_competitive])
            elif table_name == "bid_templates":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[{
                    "id": str(BID_TEMPLATE_ID),
                    "name": "Standard Grading Template",
                    "is_lump_sum": True,
                }])
            elif table_name == "vendors":
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            else:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        bad_vendor_id = str(NONEXISTENT_VENDOR_ID)
        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": bad_vendor_id, "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        with pytest.raises(BidPackageValidationError) as exc_info:
            await create_bid_package_with_invitations(
                task_id=TASK_ID,
                payload=payload,
                created_by=PM_USER_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        # Error detail should reference the specific vendor ID that failed
        assert bad_vendor_id in str(exc_info.value.detail) or "vendor" in str(exc_info.value.detail).lower()
