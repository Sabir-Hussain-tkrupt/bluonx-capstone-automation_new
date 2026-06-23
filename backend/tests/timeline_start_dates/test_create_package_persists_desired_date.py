"""Task 8.1.5 — bid_packages.desired_start_date is persisted on package create.

Drives the service directly. Creation is atomic via the
fn_create_bid_package_with_invitations RPC, so the desired_start_date is asserted
on the RPC params (p_desired_start_date) rather than a table insert payload.
"""

from __future__ import annotations

import pytest

from app.services.bid_package_service import create_bid_package_with_invitations

from .conftest import (
    BID_PACKAGE_ID,
    DESIRED_START_ISO,
    PM_USER_ID,
    TASK_ID,
)


def _create_rpc_params(mock_supabase_admin) -> dict:
    """Return the params dict passed to the creation RPC."""
    calls = [
        c
        for c in mock_supabase_admin.rpc.call_args_list
        if c.args and c.args[0] == "fn_create_bid_package_with_invitations"
    ]
    assert calls, "creation RPC should have been called"
    return calls[-1].args[1]


@pytest.mark.asyncio
async def test_desired_start_date_persisted_when_present(
    mock_supabase_admin,
    mock_email_service,
    mock_template_renderer,
    base_package_payload,
):
    payload = {**base_package_payload, "desired_start_date": DESIRED_START_ISO}

    await create_bid_package_with_invitations(
        task_id=TASK_ID,
        payload=payload,
        created_by=PM_USER_ID,
        db=mock_supabase_admin,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    params = _create_rpc_params(mock_supabase_admin)
    assert params.get("p_desired_start_date") == DESIRED_START_ISO


@pytest.mark.asyncio
async def test_desired_start_date_null_when_omitted(
    mock_supabase_admin,
    mock_email_service,
    mock_template_renderer,
    base_package_payload,
):
    # Omit desired_start_date entirely — service must NOT include a non-null
    # value in the insert row.
    await create_bid_package_with_invitations(
        task_id=TASK_ID,
        payload=base_package_payload,
        created_by=PM_USER_ID,
        db=mock_supabase_admin,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    params = _create_rpc_params(mock_supabase_admin)
    # Omitted desired_start_date must be passed to the RPC as NULL, never a
    # populated string.
    assert params.get("p_desired_start_date") is None


@pytest.mark.asyncio
async def test_response_includes_desired_start_date(
    mock_supabase_admin,
    mock_email_service,
    mock_template_renderer,
    base_package_payload,
):
    payload = {**base_package_payload, "desired_start_date": DESIRED_START_ISO}
    result = await create_bid_package_with_invitations(
        task_id=TASK_ID,
        payload=payload,
        created_by=PM_USER_ID,
        db=mock_supabase_admin,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )
    assert "desired_start_date" in result
    assert result["desired_start_date"] == DESIRED_START_ISO


@pytest.mark.asyncio
async def test_email_context_includes_desired_start_date(
    mock_supabase_admin,
    mock_email_service,
    mock_template_renderer,
    base_package_payload,
):
    """The invitation email's render context must include the desired date
    so the template can show a "Desired Start" row."""
    payload = {**base_package_payload, "desired_start_date": DESIRED_START_ISO}
    await create_bid_package_with_invitations(
        task_id=TASK_ID,
        payload=payload,
        created_by=PM_USER_ID,
        db=mock_supabase_admin,
        email_service=mock_email_service,
        template_renderer=mock_template_renderer,
    )

    # Either render or render_text was called with the date in its context.
    rendered = [
        c.args[1] for c in mock_template_renderer.render.call_args_list
    ]
    rendered_text = [
        c.args[1] for c in mock_template_renderer.render_text.call_args_list
    ]
    contexts = rendered + rendered_text
    assert any(
        ctx.get("desired_start_date") for ctx in contexts
    ), "expected desired_start_date in at least one email render context"
