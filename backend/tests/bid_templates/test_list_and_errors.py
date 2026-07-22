"""
Batched list enrichment (fix 4), error sanitization (fix 8) and the
UUID status-code alignment (fix 9).
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from postgrest.exceptions import APIError

from .conftest import (
    TEMPLATE_ID,
    TRADE_ID,
    build_simple_chain,
    build_templates_chain,
    build_trades_chain,
    make_db,
    make_template,
)


# ── Batched list enrichment ────────────────────────────────────────────────


def _list_db(templates, trades, items=None, packages=None):
    return make_db({
        "bid_templates": build_templates_chain(templates, target=templates[0] if templates else None),
        "bid_template_items": build_simple_chain(data=items or []),
        "trades": build_trades_chain(trades),
        "bid_packages": build_simple_chain(data=packages or []),
    })


def test_list_enriches_trade_name_item_count_and_in_use(client_factory, active_trade):
    t1 = make_template(name="Alpha", trade_id=TRADE_ID)
    t2 = make_template(name="Beta", template_id=uuid4())
    items = [
        {"bid_template_id": t1["id"]},
        {"bid_template_id": t1["id"]},
        {"bid_template_id": t2["id"]},
    ]
    packages = [{"bid_template_id": t2["id"]}]

    client = client_factory(_list_db([t1, t2], [active_trade], items, packages))
    resp = client.get("/api/v1/bid-templates")

    assert resp.status_code == 200, resp.text
    by_name = {row["name"]: row for row in resp.json()["items"]}

    assert by_name["Alpha"]["trade_name"] == "Grading"
    assert by_name["Alpha"]["item_count"] == 2
    assert by_name["Alpha"]["is_in_use"] is False

    assert by_name["Beta"]["trade_name"] is None
    assert by_name["Beta"]["item_count"] == 1
    assert by_name["Beta"]["is_in_use"] is True


def test_list_issues_one_query_per_related_table(client_factory, active_trade):
    """The point of the batching: three lookups total, not three per row."""
    templates = [make_template(name=f"T{i}", template_id=uuid4(), trade_id=TRADE_ID) for i in range(5)]
    db = _list_db(templates, [active_trade])

    client = client_factory(db)
    resp = client.get("/api/v1/bid-templates")
    assert resp.status_code == 200, resp.text

    assert db._recorder.chain("trades").execute.call_count == 1
    assert db._recorder.chain("bid_template_items").execute.call_count == 1
    assert db._recorder.chain("bid_packages").execute.call_count == 1


def test_empty_list_returns_zero_total(client_factory, active_trade):
    client = client_factory(_list_db([], [active_trade]))
    resp = client.get("/api/v1/bid-templates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_template_without_trade_gets_null_trade_name(client_factory, active_trade):
    t = make_template(name="General", trade_id=None)
    client = client_factory(_list_db([t], [active_trade]))
    resp = client.get("/api/v1/bid-templates")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["trade_name"] is None


# ── Pagination + sort guards ───────────────────────────────────────────────


def test_invalid_sort_by_falls_back_silently(client):
    client, _ = client
    resp = client.get("/api/v1/bid-templates?sort_by=name;DROP TABLE bid_templates")
    assert resp.status_code == 200, resp.text


def test_sort_dir_is_case_insensitive(client):
    client, _ = client
    assert client.get("/api/v1/bid-templates?sort_dir=DESC").status_code == 200
    assert client.get("/api/v1/bid-templates?sort_dir=nonsense").status_code == 200


def test_page_size_over_max_rejected(client):
    client, _ = client
    assert client.get("/api/v1/bid-templates?page_size=101").status_code == 422
    assert client.get("/api/v1/bid-templates?page=0").status_code == 422
    assert client.get("/api/v1/bid-templates?page_size=0").status_code == 422


def test_search_with_wildcards_does_not_error(client):
    client, _ = client
    for term in ("100%", "a_b", "O'Brien", "(paren)", "a,b"):
        assert client.get("/api/v1/bid-templates", params={"search": term}).status_code == 200


# ── UUID handling (fix 9) ──────────────────────────────────────────────────


def test_malformed_trade_id_filter_returns_422(client):
    """Was 400, while a malformed path UUID was 422. One error class, one code."""
    client, _ = client
    resp = client.get("/api/v1/bid-templates?trade_id=not-a-uuid")
    assert resp.status_code == 422, resp.text


def test_null_trade_id_filter_is_accepted(client):
    client, _ = client
    assert client.get("/api/v1/bid-templates?trade_id=null").status_code == 200


def test_malformed_path_uuid_returns_422(client):
    client, _ = client
    assert client.get("/api/v1/bid-templates/not-a-uuid").status_code == 422


# ── Error sanitization (fix 8) ─────────────────────────────────────────────


def _api_error() -> APIError:
    return APIError({
        "message": 'duplicate key value violates unique constraint "bid_templates_pkey"',
        "code": "23505",
        "hint": None,
        "details": "Key (id)=(...) already exists.",
    })


def test_db_rejection_does_not_leak_postgres_text(client_factory, active_trade):
    """The insert blows up; the client must not see constraint names.

    Only `.insert()` is made to fail — the name-uniqueness probe on the same
    table has to keep working, or the request never reaches the insert.
    """
    templates_chain = build_templates_chain([], target=None)
    templates_chain.insert.side_effect = _api_error()

    db = make_db({
        "bid_templates": templates_chain,
        "bid_template_items": build_simple_chain(data=[]),
        "trades": build_trades_chain([active_trade]),
        "bid_packages": build_simple_chain(data=[]),
    })

    client = client_factory(db)
    resp = client.post(
        "/api/v1/bid-templates",
        json={"name": "Anything", "trade_id": None, "is_lump_sum": True, "items": []},
    )

    assert resp.status_code in (422, 502), resp.text
    body = resp.text.lower()
    assert "constraint" not in body
    assert "bid_templates_pkey" not in body
    assert "23505" not in body
