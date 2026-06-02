"""
Edit-guard tests for PUT /bid-templates/{id}.

Acceptance criterion (Task 8.1): when a template is referenced by any
non-cancelled bid_package, the PUT must 409 *before any mutation*:
no metadata update, no bid_template_items delete, no _insert_items.
"""

from __future__ import annotations

import pytest

from .conftest import TEMPLATE_ID


PUT_PAYLOAD = {
    "name": "Renamed Template",
    "trade_id": None,
    "is_lump_sum": True,
    "items": [
        {
            "description": "New mob",
            "item_type": "lump_sum",
            "unit_of_measure": None,
        },
    ],
}


def _assert_no_mutation_occurred(db):
    """No write call should have been made on bid_templates or bid_template_items."""
    bt_chain = db._recorder.chain("bid_templates")
    bti_chain = db._recorder.chain("bid_template_items")

    bt_chain.update.assert_not_called()
    bt_chain.insert.assert_not_called()
    bt_chain.delete.assert_not_called()

    bti_chain.delete.assert_not_called()
    bti_chain.insert.assert_not_called()


@pytest.mark.parametrize(
    "client_fixture",
    ["client_live_open", "client_live_closed", "client_live_evaluating"],
)
def test_put_rejected_with_409_when_template_in_use(client_fixture, request):
    client, db = request.getfixturevalue(client_fixture)

    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json=PUT_PAYLOAD)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "locked" in detail.lower() or "in use" in detail.lower()
    # Message must name the referencing task and its status so the PM
    # knows *which* package blocks the edit.
    assert "duplicate" in detail.lower()
    assert any(
        keyword in detail.lower()
        for keyword in ("rough grading", "mass excavation", "storm drain")
    ), f"Expected blocking task name in detail: {detail!r}"
    assert any(
        s in detail.lower() for s in ("open", "closed", "evaluating")
    ), f"Expected blocking status in detail: {detail!r}"

    _assert_no_mutation_occurred(db)


def test_put_succeeds_when_only_cancelled_references(client_cancelled_only):
    client, db = client_cancelled_only

    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json=PUT_PAYLOAD)

    assert resp.status_code == 200, resp.text


def test_put_succeeds_when_no_references(client_no_refs):
    client, db = client_no_refs

    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json=PUT_PAYLOAD)

    assert resp.status_code == 200, resp.text


def test_put_409_caps_long_package_list_with_overflow_indicator(client_many_live):
    """Five live packages -> 409 message shows 3 by name + '+2 more'."""
    client, db = client_many_live

    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json=PUT_PAYLOAD)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "Task 0" in detail
    assert "Task 1" in detail
    assert "Task 2" in detail
    assert "Task 3" not in detail
    assert "Task 4" not in detail
    assert "+2 more" in detail
    _assert_no_mutation_occurred(db)


def test_put_rejected_when_mixed_open_and_cancelled(client_mixed):
    """One open + one cancelled. Still locked; message names the open one."""
    client, db = client_mixed

    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json=PUT_PAYLOAD)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "rough grading" in detail.lower()
    # The cancelled task ("Cancelled Scope") must NOT be the one named as blocker.
    # We don't forbid it from appearing anywhere, but the live one must.
    _assert_no_mutation_occurred(db)
