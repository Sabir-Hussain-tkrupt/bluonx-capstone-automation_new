"""Signed Scope of Work — mandatory SoW document on bid-package creation.

The PM must supply a scope_of_work_document_id that resolves to a
project_documents row in the task's project with document_kind='scope_of_work'.
These tests drive the real create service with an op-aware Supabase mock.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.bid_package_service import (
    BidPackageValidationError,
    create_bid_package_with_invitations,
)

from .conftest import (
    BID_TEMPLATE_ID,
    PM_USER_ID,
    PROJECT_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

SOW_DOC_ID = uuid4()


def _sow_doc(*, project_id=str(PROJECT_ID), document_kind="scope_of_work"):
    return {
        "id": str(SOW_DOC_ID),
        "project_id": project_id,
        "file_name": "scope-of-work.pdf",
        "document_kind": document_kind,
    }


def _make_table_side_effect(task, sow_doc):
    """Op-aware table mock: valid task/template/vendor/contact + a SoW doc."""

    def table_side_effect(table_name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.single.return_value = chain
        chain.in_.return_value = chain

        if table_name == "tasks":
            chain.execute.return_value = MagicMock(data=[task])
            update_result = MagicMock()
            update_result.eq.return_value = update_result
            update_result.execute.return_value = MagicMock(data=[task])
            chain.update.return_value = update_result
        elif table_name == "bid_templates":
            chain.execute.return_value = MagicMock(data=[{
                "id": str(BID_TEMPLATE_ID),
                "name": "Standard Grading Template",
                "is_lump_sum": True,
            }])
        elif table_name == "projects":
            chain.execute.return_value = MagicMock(data=[{
                "id": str(PROJECT_ID),
                "name": "Sunrise Meadows Phase 2",
            }])
        elif table_name == "vendors":
            chain.execute.return_value = MagicMock(data=[{
                "id": str(VENDOR_IDS[0]),
                "company_name": "Smith Grading Co.",
                "status": "active",
                "deleted_at": None,
            }])
        elif table_name == "vendor_contacts":
            chain.execute.return_value = MagicMock(data=[{
                "id": str(VENDOR_CONTACT_IDS[0]),
                "vendor_id": str(VENDOR_IDS[0]),
                "full_name": "John Smith",
                "email": "john@smithgrading.com",
            }])
        elif table_name == "project_documents":
            chain.execute.return_value = MagicMock(data=[sow_doc] if sow_doc else [])
        elif table_name == "users":
            chain.execute.return_value = MagicMock(data=[{
                "id": str(PM_USER_ID),
                "full_name": "Alex Rivera",
                "email": "pm@bluonx.dev",
            }])
        elif table_name == "bid_packages":
            insert_result = MagicMock()
            insert_result.execute.return_value = MagicMock(data=[{
                "id": str(uuid4()),
                "task_id": str(TASK_ID),
                "round_number": 1,
                "status": "open",
            }])
            chain.insert.return_value = insert_result
        else:
            result = MagicMock()
            result.execute.return_value = MagicMock(data=[])
            result.eq.return_value = result
            chain.insert.return_value = result
            chain.update.return_value = result
            chain.execute.return_value = MagicMock(data=[])
        return chain

    return table_side_effect


def _payload(future_deadline, *, sow_id=str(SOW_DOC_ID)):
    p = {
        "task_id": str(TASK_ID),
        "bid_template_id": str(BID_TEMPLATE_ID),
        "deadline": future_deadline.isoformat(),
        "project_document_ids": [],
        "vendor_selections": [
            {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
        ],
    }
    if sow_id is not None:
        p["scope_of_work_document_id"] = sow_id
    return p


async def _run(mock_supabase, payload, mock_email_service, mock_template_renderer):
    return await create_bid_package_with_invitations(
        task_id=TASK_ID,
        payload=payload,
        created_by=PM_USER_ID,
        db=mock_supabase,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )


@pytest.mark.asyncio
async def test_missing_sow_document_returns_422(
    mock_supabase, mock_email_service, mock_template_renderer,
    sample_task_competitive, future_deadline,
):
    mock_supabase.table.side_effect = _make_table_side_effect(sample_task_competitive, None)
    with pytest.raises(BidPackageValidationError) as exc:
        await _run(mock_supabase, _payload(future_deadline, sow_id=None),
                   mock_email_service, mock_template_renderer)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_sow_wrong_document_kind_returns_422(
    mock_supabase, mock_email_service, mock_template_renderer,
    sample_task_competitive, future_deadline,
):
    mock_supabase.table.side_effect = _make_table_side_effect(
        sample_task_competitive, _sow_doc(document_kind="reference")
    )
    with pytest.raises(BidPackageValidationError) as exc:
        await _run(mock_supabase, _payload(future_deadline),
                   mock_email_service, mock_template_renderer)
    assert exc.value.status_code == 422
    assert "scope_of_work" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_sow_from_foreign_project_returns_422(
    mock_supabase, mock_email_service, mock_template_renderer,
    sample_task_competitive, future_deadline,
):
    mock_supabase.table.side_effect = _make_table_side_effect(
        sample_task_competitive, _sow_doc(project_id=str(uuid4()))
    )
    with pytest.raises(BidPackageValidationError) as exc:
        await _run(mock_supabase, _payload(future_deadline),
                   mock_email_service, mock_template_renderer)
    assert exc.value.status_code == 422
    assert "project" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_happy_path_passes_sow_id_to_rpc(
    mock_supabase, mock_email_service, mock_template_renderer,
    sample_task_competitive, future_deadline,
):
    mock_supabase.table.side_effect = _make_table_side_effect(
        sample_task_competitive, _sow_doc()
    )
    await _run(mock_supabase, _payload(future_deadline),
               mock_email_service, mock_template_renderer)

    rpc_calls = [
        c for c in mock_supabase.rpc.call_args_list
        if c.args and c.args[0] == "fn_create_bid_package_with_invitations"
    ]
    assert len(rpc_calls) == 1
    params = rpc_calls[0].args[1]
    assert params["p_scope_of_work_document_id"] == str(SOW_DOC_ID)
