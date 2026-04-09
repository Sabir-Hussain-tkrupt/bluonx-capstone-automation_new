"""
Email rendering integration tests for bid package creation.

Verifies that the template renderer receives the correct context variables
and that both HTML and plain text versions are rendered and sent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult

from .conftest import (
    BID_TEMPLATE_ID,
    DOC_IDS,
    PM_USER_ID,
    PORTAL_BASE_URL,
    PROJECT_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

# This import will fail until the service is implemented — expected for test-first.
from app.services.bid_package_service import create_bid_package_with_invitations


def _setup_rendering_mocks(mock_supabase, deadline_iso: str, pm_user: dict, task: dict):
    """Configure mocks that expose template rendering context."""
    bid_package_id = uuid4()
    render_contexts: list[dict] = []
    render_text_contexts: list[dict] = []

    def table_side_effect(table_name):
        chain = MagicMock()

        if table_name == "bid_packages":
            insert_result = MagicMock()
            insert_result.execute.return_value = MagicMock(data=[{
                "id": str(bid_package_id),
                "task_id": str(TASK_ID),
                "round_number": 1,
                "deadline": deadline_iso,
                "status": "open",
                "bid_template_id": str(BID_TEMPLATE_ID),
                "created_by": str(PM_USER_ID),
            }])
            chain.insert.return_value = insert_result
        elif table_name == "tasks":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.is_.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[task])
            update_result = MagicMock()
            update_result.eq.return_value = update_result
            update_result.execute.return_value = MagicMock(data=[task])
            chain.update.return_value = update_result
        elif table_name == "users":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[pm_user])
        elif table_name == "projects":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[{
                "id": str(PROJECT_ID),
                "name": "Sunrise Meadows Phase 2",
            }])
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
            chain.execute.return_value = MagicMock(data=[
                {"id": str(DOC_IDS[0]), "project_id": str(PROJECT_ID), "file_name": "grading_plan.pdf"},
                {"id": str(DOC_IDS[1]), "project_id": str(PROJECT_ID), "file_name": "site_survey.dwg"},
            ])
            chain.in_.return_value = chain
        elif table_name == "vendor_contacts":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[{
                "id": str(VENDOR_CONTACT_IDS[0]),
                "vendor_id": str(VENDOR_IDS[0]),
                "full_name": "John Smith",
                "email": "john@smithgrading.com",
            }])
        elif table_name == "vendors":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[{
                "id": str(VENDOR_IDS[0]),
                "company_name": "Smith Grading Co.",
                "status": "active",
                "deleted_at": None,
            }])
        else:
            result = MagicMock()
            result.execute.return_value = MagicMock(data=[])
            chain.insert.return_value = result
            chain.select.return_value = chain
            chain.update.return_value = result
            chain.eq.return_value = chain
            chain.single.return_value = chain
            result.eq.return_value = result
            chain.execute.return_value = MagicMock(data=[])

        return chain

    mock_supabase.table.side_effect = table_side_effect
    return bid_package_id, render_contexts, render_text_contexts


class TestEmailContextVariables:
    """Email template receives all required context variables."""

    @pytest.mark.asyncio
    async def test_email_rendered_with_correct_context(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        sample_pm_user,
        future_deadline,
    ):
        """The template renderer is called with vendor name, project name, task name, etc."""
        bid_package_id, _, _ = _setup_rendering_mocks(
            mock_supabase,
            future_deadline.isoformat(),
            sample_pm_user,
            sample_task_competitive,
        )

        # Capture render calls to inspect context
        render_contexts: list[dict] = []

        def capture_render(template_name, context):
            render_contexts.append(context)
            return "<html><body>Bid Invitation Email</body></html>"

        def capture_render_text(template_name, context):
            return "Bid Invitation Email (plain text)"

        mock_template_renderer.render.side_effect = capture_render
        mock_template_renderer.render_text.side_effect = capture_render_text

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [str(DOC_IDS[0]), str(DOC_IDS[1])],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(render_contexts) >= 1, "Template renderer should be called at least once"

        ctx = render_contexts[0]

        # Vendor contact name
        assert "vendor_contact_name" in ctx or "contact_name" in ctx, (
            "Context must include vendor contact name"
        )
        contact_name = ctx.get("vendor_contact_name") or ctx.get("contact_name")
        assert contact_name == "John Smith"

        # Project name
        assert "project_name" in ctx
        assert ctx["project_name"] == "Sunrise Meadows Phase 2"

        # Task name
        assert "task_name" in ctx
        assert ctx["task_name"] == "Rough Grading"

        # Deadline
        assert "deadline" in ctx

        # Bid format (lump sum vs unit price)
        assert "bid_format" in ctx or "is_lump_sum" in ctx, (
            "Context must include bid format information"
        )

        # Document names
        assert "document_names" in ctx or "documents" in ctx, (
            "Context must include document names"
        )
        docs = ctx.get("document_names") or ctx.get("documents")
        assert len(docs) == 2

        # Magic link URL
        assert "magic_link_url" in ctx
        assert ctx["magic_link_url"].startswith(PORTAL_BASE_URL)


class TestHTMLAndPlainTextRendering:
    """Both HTML and plain text versions must be rendered and sent."""

    @pytest.mark.asyncio
    async def test_both_html_and_text_versions_sent(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        sample_pm_user,
        future_deadline,
    ):
        """EmailService receives both html_body and plain_text_body."""
        _setup_rendering_mocks(
            mock_supabase,
            future_deadline.isoformat(),
            sample_pm_user,
            sample_task_competitive,
        )

        mock_template_renderer.render.return_value = "<html><body>HTML version</body></html>"
        mock_template_renderer.render_text.return_value = "Plain text version"

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # Both render and render_text should have been called
        assert mock_template_renderer.render.call_count >= 1, (
            "HTML template render should be called"
        )
        assert mock_template_renderer.render_text.call_count >= 1, (
            "Plain text template render should be called"
        )

        # EmailService should receive both versions
        call_kwargs = mock_email_service.send_email.call_args.kwargs
        assert "html_body" in call_kwargs
        assert "plain_text_body" in call_kwargs
        assert len(call_kwargs["html_body"]) > 0
        assert len(call_kwargs["plain_text_body"]) > 0


class TestPMInfoInEmail:
    """The PM's name and email must appear in the email context."""

    @pytest.mark.asyncio
    async def test_pm_name_and_email_in_context(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        sample_pm_user,
        future_deadline,
    ):
        """The PM (created_by user) name and email appear in the template context."""
        _setup_rendering_mocks(
            mock_supabase,
            future_deadline.isoformat(),
            sample_pm_user,
            sample_task_competitive,
        )

        render_contexts: list[dict] = []

        def capture_render(template_name, context):
            render_contexts.append(context)
            return "<html><body>Email</body></html>"

        mock_template_renderer.render.side_effect = capture_render

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(render_contexts) >= 1
        ctx = render_contexts[0]

        # PM name
        assert "pm_name" in ctx or "sender_name" in ctx, (
            "Context must include PM name"
        )
        pm_name = ctx.get("pm_name") or ctx.get("sender_name")
        assert pm_name == "Alex Rivera"

        # PM email
        assert "pm_email" in ctx or "sender_email" in ctx, (
            "Context must include PM email"
        )
        pm_email = ctx.get("pm_email") or ctx.get("sender_email")
        assert pm_email == "pm@bluonx.dev"
