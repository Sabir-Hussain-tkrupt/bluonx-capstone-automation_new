"""
Input validation on POST/PUT /bid-templates (fixes 2, 3, 7).

Each test states the blueprint rule it pins, because several of these
scenarios passed silently before and would regress invisibly.
"""

from __future__ import annotations

import pytest

from .conftest import TEMPLATE_ID, TRADE_ID


def _valid_create(**overrides) -> dict:
    payload = {
        "name": "New Template",
        "trade_id": None,
        "is_lump_sum": True,
        "items": [],
    }
    payload.update(overrides)
    return payload


def _valid_put(**overrides) -> dict:
    payload = {
        "name": "Renamed Template",
        "trade_id": None,
        "is_lump_sum": True,
        "items": [],
    }
    payload.update(overrides)
    return payload


# ── Whitespace trimming (fix 2) ────────────────────────────────────────────


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n  "])
def test_whitespace_only_name_rejected(client, blank):
    """Trim runs before min_length, so a blank name fails instead of storing empty."""
    client, _ = client
    resp = client.post("/api/v1/bid-templates", json=_valid_create(name=blank))
    assert resp.status_code == 422, resp.text


def test_name_is_stored_trimmed(client):
    client, db = client
    resp = client.post(
        "/api/v1/bid-templates", json=_valid_create(name="  Padded Name  ")
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Padded Name"


def test_whitespace_only_item_description_rejected(client):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates",
        json=_valid_create(
            is_lump_sum=False,
            items=[{"description": "   ", "item_type": "lump_sum"}],
        ),
    )
    assert resp.status_code == 422, resp.text


def test_whitespace_unit_of_measure_rejected_for_unit_price(client):
    """The one validator the task spec calls for, previously defeated by
    whitespace: "  " is truthy, so `if not self.unit_of_measure` passed."""
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates",
        json=_valid_create(
            is_lump_sum=False,
            items=[
                {
                    "description": "Excavation",
                    "item_type": "unit_price",
                    "unit_of_measure": "   ",
                }
            ],
        ),
    )
    assert resp.status_code == 422, resp.text


def test_missing_unit_of_measure_rejected_for_unit_price(client):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates",
        json=_valid_create(
            is_lump_sum=False,
            items=[{"description": "Excavation", "item_type": "unit_price"}],
        ),
    )
    assert resp.status_code == 422, resp.text


def test_unit_price_item_with_unit_of_measure_accepted(client):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates",
        json=_valid_create(
            is_lump_sum=False,
            items=[
                {
                    "description": "Excavation",
                    "item_type": "unit_price",
                    "unit_of_measure": "CY",
                }
            ],
        ),
    )
    assert resp.status_code == 201, resp.text


# ── is_lump_sum / items relationship (fix 3) ───────────────────────────────


def test_structured_template_requires_items(client):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates", json=_valid_create(is_lump_sum=False, items=[])
    )
    assert resp.status_code == 422, resp.text


def test_lump_sum_template_rejects_items(client):
    """Previously accepted: items were stored but ignored by the submit
    validator, so the preview and the vendor form disagreed."""
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates",
        json=_valid_create(
            is_lump_sum=True,
            items=[{"description": "Mobilization", "item_type": "lump_sum"}],
        ),
    )
    assert resp.status_code == 422, resp.text
    assert "lump-sum" in resp.text.lower()


def test_lump_sum_template_rejects_items_on_put(client):
    client, _ = client
    resp = client.put(
        f"/api/v1/bid-templates/{TEMPLATE_ID}",
        json=_valid_put(
            is_lump_sum=True,
            items=[{"description": "Mobilization", "item_type": "lump_sum"}],
        ),
    )
    assert resp.status_code == 422, resp.text


def test_bad_item_type_rejected(client):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates",
        json=_valid_create(
            is_lump_sum=False,
            items=[{"description": "Mob", "item_type": "not_a_type"}],
        ),
    )
    assert resp.status_code == 422, resp.text


# ── PUT full-replace semantics (fix 7) ─────────────────────────────────────


@pytest.mark.parametrize("omitted", ["trade_id", "is_lump_sum", "items"])
def test_put_rejects_omitted_field(client, omitted):
    """Omission used to mean "reset this": a dropped trade_id silently cleared
    the association, a dropped is_lump_sum silently forced lump-sum."""
    client, _ = client
    payload = _valid_put()
    payload.pop(omitted)
    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json=payload)
    assert resp.status_code == 422, resp.text


def test_put_accepts_explicit_null_trade_id(client):
    """Clearing the association is still possible — explicitly."""
    client, _ = client
    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json=_valid_put())
    assert resp.status_code == 200, resp.text


def test_put_rejects_empty_body(client):
    client, _ = client
    resp = client.put(f"/api/v1/bid-templates/{TEMPLATE_ID}", json={})
    assert resp.status_code == 422, resp.text


def test_create_still_allows_omitted_optional_fields(client):
    """POST keeps its defaults — only PUT is full-replace."""
    client, _ = client
    resp = client.post("/api/v1/bid-templates", json={"name": "Minimal"})
    assert resp.status_code == 201, resp.text
