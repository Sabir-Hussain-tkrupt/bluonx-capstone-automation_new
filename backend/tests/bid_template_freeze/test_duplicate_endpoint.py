"""
Tests for POST /bid-templates/{id}/duplicate.

This is the "escape hatch" that makes the freeze rule non-blocking:
when a template is locked, the PM duplicates it, edits the copy, and
points the next round at it.
"""

from __future__ import annotations

from unittest.mock import call

from .conftest import (
    NONEXISTENT_TEMPLATE_ID,
    PM_USER_ID,
    TEMPLATE_ID,
)


def test_duplicate_returns_new_template_with_copied_metadata(client_no_refs):
    client, db = client_no_refs

    resp = client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    # New row, not the source
    assert body["id"] != str(TEMPLATE_ID)
    assert body["name"].startswith("Copy of ")
    assert "Standard Grading Template" in body["name"]
    assert body["created_by"] == str(PM_USER_ID)
    assert body["is_lump_sum"] is False  # carried from source
    # Items array is populated from the source items (verified separately)
    assert "items" in body


def test_duplicate_inserts_template_with_correct_payload(client_no_refs):
    client, db = client_no_refs

    client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")

    bt_chain = db._recorder.chain("bid_templates")
    # The single insert call carries the source-derived fields.
    inserts = bt_chain.insert.call_args_list
    assert len(inserts) == 1
    payload = inserts[0][0][0]
    assert payload["name"].startswith("Copy of ")
    assert payload["created_by"] == str(PM_USER_ID)
    assert payload["is_lump_sum"] is False
    # trade_id copied through (string form, like source)
    assert payload["trade_id"] is not None


def test_duplicate_inserts_items_with_fresh_ids_and_preserved_fields(client_no_refs):
    client, db = client_no_refs

    client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")

    bti_chain = db._recorder.chain("bid_template_items")
    inserts = bti_chain.insert.call_args_list
    assert len(inserts) == 1, "items should be inserted in a single bulk call"
    rows = inserts[0][0][0]
    assert len(rows) == 3, f"expected 3 item copies, got {len(rows)}"

    # Source descriptions preserved, ordered by sort_order.
    descriptions = [r["description"] for r in rows]
    assert descriptions == ["Mobilization", "Excavation", "Final grade"]

    # New rows must NOT carry the source ids; _insert_items lets the DB
    # generate fresh UUIDs.
    for r in rows:
        assert "id" not in r or r["id"] is None

    # Each row points at the NEW template, not the source.
    new_template_ids = {r["bid_template_id"] for r in rows}
    assert len(new_template_ids) == 1
    assert str(TEMPLATE_ID) not in new_template_ids

    # item_type + unit_of_measure preserved per row.
    assert rows[1]["item_type"] == "unit_price"
    assert rows[1]["unit_of_measure"] == "CY"


def test_duplicate_does_not_mutate_source_template(client_no_refs):
    client, db = client_no_refs

    client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")

    bt_chain = db._recorder.chain("bid_templates")
    # The duplicate flow must never UPDATE or DELETE on bid_templates.
    bt_chain.update.assert_not_called()
    bt_chain.delete.assert_not_called()


def test_duplicate_404_when_source_missing(client_template_missing):
    client, db = client_template_missing

    resp = client.post(f"/api/v1/bid-templates/{NONEXISTENT_TEMPLATE_ID}/duplicate")

    assert resp.status_code == 404, resp.text


def test_duplicate_allowed_when_source_is_in_use(client_live_open):
    """The whole point of the escape hatch: locked templates can still be duplicated."""
    client, db = client_live_open

    resp = client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")

    assert resp.status_code == 201, resp.text
