"""
Trade validation (fixes 1, 5) and the duplicate-name policy (fix 6).
"""

from __future__ import annotations

from uuid import uuid4

from .conftest import (
    INACTIVE_TRADE_ID,
    TEMPLATE_ID,
    TRADE_ID,
    build_simple_chain,
    build_templates_chain,
    build_trades_chain,
    make_db,
    make_template,
)


def _create(**overrides) -> dict:
    payload = {"name": "New Template", "trade_id": None, "is_lump_sum": True, "items": []}
    payload.update(overrides)
    return payload


def _put(**overrides) -> dict:
    payload = {"name": "Renamed", "trade_id": None, "is_lump_sum": True, "items": []}
    payload.update(overrides)
    return payload


# ── Trade validation ───────────────────────────────────────────────────────


def test_unknown_trade_id_returns_422_not_502(client):
    """The headline bug: .single() raised on zero rows, the except caught it
    as a 502, and the 422 beneath was unreachable."""
    client, _ = client
    resp = client.post("/api/v1/bid-templates", json=_create(trade_id=str(uuid4())))
    assert resp.status_code == 422, resp.text
    assert "trade" in resp.json()["detail"].lower()


def test_inactive_trade_rejected(client):
    """Trades retire by flag, never delete; a retired trade must not be
    selectable on a new template."""
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates", json=_create(trade_id=str(INACTIVE_TRADE_ID))
    )
    assert resp.status_code == 422, resp.text


def test_active_trade_accepted(client):
    client, _ = client
    resp = client.post("/api/v1/bid-templates", json=_create(trade_id=str(TRADE_ID)))
    assert resp.status_code == 201, resp.text


def test_unknown_trade_rejected_on_put(client):
    client, _ = client
    resp = client.put(
        f"/api/v1/bid-templates/{TEMPLATE_ID}", json=_put(trade_id=str(uuid4()))
    )
    assert resp.status_code == 422, resp.text


def test_missing_template_returns_404_not_502(client_factory, active_trade):
    db = make_db({
        "bid_templates": build_templates_chain([], target=None),
        "bid_template_items": [],
        "trades": build_trades_chain([active_trade]),
        "bid_packages": build_simple_chain(data=[]),
    })
    client = client_factory(db)
    resp = client.get(f"/api/v1/bid-templates/{uuid4()}")
    assert resp.status_code == 404, resp.text


# ── Duplicate names ────────────────────────────────────────────────────────


def test_duplicate_name_rejected_on_create(client, existing_template):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates", json=_create(name=existing_template["name"])
    )
    assert resp.status_code == 409, resp.text


def test_duplicate_name_is_case_insensitive(client, existing_template):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates", json=_create(name=existing_template["name"].upper())
    )
    assert resp.status_code == 409, resp.text


def test_duplicate_name_is_whitespace_insensitive(client, existing_template):
    client, _ = client
    resp = client.post(
        "/api/v1/bid-templates", json=_create(name=f"  {existing_template['name']}  ")
    )
    assert resp.status_code == 409, resp.text


def test_distinct_name_accepted(client):
    client, _ = client
    resp = client.post("/api/v1/bid-templates", json=_create(name="Totally Different"))
    assert resp.status_code == 201, resp.text


def test_put_keeping_own_name_is_not_a_conflict(client, existing_template):
    """Self-exclusion: re-saving without renaming must not 409 against itself."""
    client, _ = client
    resp = client.put(
        f"/api/v1/bid-templates/{TEMPLATE_ID}", json=_put(name=existing_template["name"])
    )
    assert resp.status_code == 200, resp.text


def test_put_taking_another_templates_name_is_rejected(
    client_factory, existing_template, active_trade
):
    other = make_template(name="Someone Else's Name", template_id=uuid4())
    db = make_db({
        "bid_templates": build_templates_chain(
            [existing_template, other], target=existing_template
        ),
        "bid_template_items": [],
        "trades": build_trades_chain([active_trade]),
        "bid_packages": build_simple_chain(data=[]),
    })
    client = client_factory(db)
    resp = client.put(
        f"/api/v1/bid-templates/{TEMPLATE_ID}", json=_put(name="someone else's name")
    )
    assert resp.status_code == 409, resp.text


# ── Duplicate endpoint name resolution ─────────────────────────────────────


def test_duplicate_uses_copy_of_prefix(client, existing_template):
    client, _ = client
    resp = client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == f"Copy of {existing_template['name']}"


def test_second_duplicate_gets_numeric_suffix(
    client_factory, existing_template, active_trade
):
    """Duplicating twice collides by construction. Duplicate is the escape
    hatch for the freeze guard, so it must never start returning 409s."""
    first_copy = make_template(
        name=f"Copy of {existing_template['name']}", template_id=uuid4()
    )
    db = make_db({
        "bid_templates": build_templates_chain(
            [existing_template, first_copy], target=existing_template
        ),
        "bid_template_items": [],
        "trades": build_trades_chain([active_trade]),
        "bid_packages": build_simple_chain(data=[]),
    })
    client = client_factory(db)
    resp = client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == f"Copy of {existing_template['name']} (2)"


def test_third_duplicate_increments_suffix(
    client_factory, existing_template, active_trade
):
    base = f"Copy of {existing_template['name']}"
    roster = [
        existing_template,
        make_template(name=base, template_id=uuid4()),
        make_template(name=f"{base} (2)", template_id=uuid4()),
    ]
    db = make_db({
        "bid_templates": build_templates_chain(roster, target=existing_template),
        "bid_template_items": [],
        "trades": build_trades_chain([active_trade]),
        "bid_packages": build_simple_chain(data=[]),
    })
    client = client_factory(db)
    resp = client.post(f"/api/v1/bid-templates/{TEMPLATE_ID}/duplicate")
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == f"{base} (3)"
