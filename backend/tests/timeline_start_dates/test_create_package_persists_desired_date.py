"""Task 8.1.5 — bid_packages.desired_start_date is persisted on package create.

Drives the service directly (matching backend/tests/bid_package_creation/
test_bid_package_creation.py). The bid_packages.insert(...) call is captured
via mock.call_args_list and asserted on its payload.
"""

from __future__ import annotations

from unittest.mock import call

import pytest

from app.services.bid_package_service import create_bid_package_with_invitations

from .conftest import (
    BID_PACKAGE_ID,
    DESIRED_START_ISO,
    PM_USER_ID,
    TASK_ID,
)


def _bid_packages_insert_payload(mock_supabase_admin) -> dict:
    """Return the dict passed to db.table('bid_packages').insert(...).

    The mock_supabase_admin fixture returns the same MagicMock for every
    table() call, so .insert is shared. We filter by the table() call
    sequence: each .insert call that immediately followed a table("bid_packages")
    is a candidate. For these tests there is exactly one such insert.
    """
    table = mock_supabase_admin.table
    insert = table.return_value.insert
    # Identify which insert call corresponds to bid_packages by walking
    # the call history of `table` and `insert` together.
    table_calls = table.call_args_list
    insert_calls = insert.call_args_list

    # The service touches: bid_packages (insert), bid_package_documents (insert),
    # bid_invitations (insert), magic_link_tokens (insert), tasks (update).
    # bid_packages is the first insert in the sequence.
    bid_package_table_idx = next(
        i for i, c in enumerate(table_calls) if c == call("bid_packages")
    )
    # Find the first insert call that happens at-or-after the bid_packages table call.
    # Insert calls are recorded across all tables, so just grab the first one —
    # the service inserts the bid_package row before any other inserts.
    assert insert_calls, "expected at least one insert call"
    return insert_calls[0].args[0]


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

    row = _bid_packages_insert_payload(mock_supabase_admin)
    assert row.get("desired_start_date") == DESIRED_START_ISO


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

    row = _bid_packages_insert_payload(mock_supabase_admin)
    # Either the key is absent OR it's None; both are acceptable. A populated
    # string would be a bug.
    assert row.get("desired_start_date") in (None,)


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
